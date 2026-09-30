"""Hybrid index over one (chunking strategy, embedding model) pair.

Dense: FAISS (Flat = exact, HNSW = approximate) or ChromaDB (persisted, native metadata filtering) - one interface.
Lexical: BM25 (rank-bm25). Fusion: Reciprocal Rank Fusion.
"""

import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict
from rank_bm25 import BM25Okapi

from yokoten.config import settings
from yokoten.db import Chunk, Document, select, session
from yokoten.domain import DOC_TYPE_LABEL
from yokoten.retrieval.embeddings import EmbeddingCache, embed_query, slug

RRF_K = 60
_TOK = re.compile(r"[a-z0-9]+(?:[-/.][a-z0-9]+)*")
STOP = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "which",
        "who",
        "why",
        "with",
        "did",
        "does",
        "do",
    ]
)
FILTER_FIELDS = ("doc_type", "product_line", "component", "project", "plant", "classification", "collection")
# "compatible-with" fields: a document with no value (e.g. a supplier report has no component) is not excluded
SOFT_FIELDS = ("product_line", "component", "project", "plant")
VERSION_FILE = settings.var_dir / "index_version.txt"


def tokenize(text: str) -> list[str]:
    out = []
    for t in _TOK.findall(text.lower()):
        if t in STOP:
            continue
        out.append(t)
        if any(c in t for c in "-/."):
            out += [p for p in re.split(r"[-/.]", t) if p and p not in STOP]
    return out


def index_version() -> str:
    return VERSION_FILE.read_text() if VERSION_FILE.exists() else "0"


def bump_index_version() -> None:
    VERSION_FILE.write_text(str(int(index_version()) + 1))


@dataclass
class Hit:
    idx: int
    chunk_id: str
    dense: float | None = None
    dense_rank: int | None = None
    bm25: float | None = None
    bm25_rank: int | None = None
    fused: float = 0.0
    rerank: float | None = None
    meta: dict = field(default_factory=dict)


class Index:
    def __init__(self, strategy: str, model: str, collections: tuple[str, ...] = ("engineering",)):
        """One index per (chunking, embedding model, set of collections) - like separate vector-DB collections."""
        self.strategy, self.model, self.collections = strategy, model, tuple(sorted(collections))
        t0 = time.perf_counter()
        with session() as s:
            docs = {
                d.rev_key: d
                for d in s.exec(
                    select(Document).where(
                        Document.status == "ready", Document.collection.in_(self.collections)
                    )
                ).all()
            }
            chunks = [
                c
                for c in s.exec(select(Chunk).where(Chunk.strategy == strategy, Chunk.kind != "parent")).all()
                if c.rev_key in docs
            ]
        chunks.sort(key=lambda c: c.id)
        self.ids = [c.id for c in chunks]
        self.chunks = chunks
        self.meta = []
        self.embed_texts = []
        for c in chunks:
            d = docs[c.rev_key]
            self.meta.append(
                {
                    "doc_id": d.doc_id,
                    "rev_key": d.rev_key,
                    "title": d.title,
                    "doc_type": d.doc_type,
                    "product_line": d.product_line,
                    "component": d.component,
                    "project": d.project,
                    "plant": d.plant,
                    "year": d.year,
                    "classification": d.classification,
                    "collection": d.collection,
                    "is_latest": d.is_latest,
                    "revision": d.revision,
                }
            )
            self.embed_texts.append(self.header(d, c) + c.text)
        self._arrays = {f: np.array([m[f] or "" for m in self.meta], dtype=object) for f in FILTER_FIELDS}
        self._years = np.array([m["year"] or 0 for m in self.meta])
        self._latest = np.array([m["is_latest"] for m in self.meta], dtype=bool)
        t1 = time.perf_counter()
        self.vecs = EmbeddingCache(model).embed(self.embed_texts)
        t2 = time.perf_counter()
        self.bm25 = BM25Okapi([tokenize(t) for t in self.embed_texts]) if chunks else None
        self.stats = {
            "chunks": len(chunks),
            "load_s": round(t1 - t0, 2),
            "embed_s": round(t2 - t1, 2),
            "bm25_s": round(time.perf_counter() - t2, 2),
            "dim": int(self.vecs.shape[1]) if chunks else 0,
        }
        self._faiss: dict = {}
        self._chroma = None

    @property
    def key(self) -> str:
        cols = (
            "" if self.collections == ("engineering",) else "__" + "+".join(c[:6] for c in self.collections)
        )
        return f"{self.strategy}__{slug(self.model)}{cols}"

    @staticmethod
    def header(d: Document, c: Chunk) -> str:
        """Contextual chunk header: every chunk carries its document identity into the embedding and BM25."""
        sec = f" - {c.section}" if c.section else ""
        return (
            f"{d.title} [{d.doc_id} rev {d.revision}] ({DOC_TYPE_LABEL.get(d.doc_type, d.doc_type)}){sec}\n"
        )

    # -------------------------------------------------------------- filters
    def mask(self, filters: dict | None) -> np.ndarray | None:
        if not filters:
            return None
        m = np.ones(len(self.ids), dtype=bool)
        for f in FILTER_FIELDS:
            if filters.get(f):
                hit = np.isin(self._arrays[f], list(filters[f]))
                m &= (hit | (self._arrays[f] == "")) if f in SOFT_FIELDS else hit
        unknown_year = self._years == 0
        if filters.get("year_min"):
            m &= (self._years >= int(filters["year_min"])) | unknown_year
        if filters.get("year_max"):
            m &= (self._years <= int(filters["year_max"])) | unknown_year
        if filters.get("latest_only"):
            m &= self._latest
        return m

    # -------------------------------------------------------------- dense stores
    def faiss_index(self, kind: str):
        if kind not in self._faiss:
            import faiss

            t = time.perf_counter()
            d = self.vecs.shape[1]
            if kind == "hnsw":
                ix = faiss.IndexHNSWFlat(d, 32, faiss.METRIC_INNER_PRODUCT)
                ix.hnsw.efConstruction = 80
            else:
                ix = faiss.IndexFlatIP(d)
            ix.add(self.vecs)
            path = settings.var_dir / "index" / f"{self.key}__{kind}.faiss"
            path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(ix, str(path))
            self.stats[f"faiss_{kind}_build_s"] = round(time.perf_counter() - t, 3)
            self.stats[f"faiss_{kind}_bytes"] = path.stat().st_size
            self._faiss[kind] = ix
        return self._faiss[kind]

    def chroma(self):
        if self._chroma is None:
            import chromadb

            t = time.perf_counter()
            client = chromadb.PersistentClient(
                path=str(settings.var_dir / "chroma"), settings=chromadb.Settings(anonymized_telemetry=False)
            )
            name = self.key.replace("_", "-").replace("__", "-")[:60]
            col = client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
            existing = set(col.get(include=[])["ids"])
            wanted = set(self.ids)
            if stale := list(existing - wanted):
                col.delete(ids=stale)
            todo = [i for i, cid in enumerate(self.ids) if cid not in existing]
            for s in range(0, len(todo), 2000):
                part = todo[s : s + 2000]
                col.add(
                    ids=[self.ids[i] for i in part],
                    embeddings=self.vecs[part],
                    metadatas=[
                        {
                            **{f: self.meta[i][f] or "" for f in FILTER_FIELDS},
                            "year": self.meta[i]["year"] or 0,
                            "is_latest": bool(self.meta[i]["is_latest"]),
                        }
                        for i in part
                    ],
                )
            self.stats["chroma_sync_s"] = round(time.perf_counter() - t, 3)
            self._chroma = col
            self._pos = {cid: i for i, cid in enumerate(self.ids)}
        return self._chroma

    @staticmethod
    def chroma_where(filters: dict | None) -> dict | None:
        if not filters:
            return None
        conds = []
        for f in FILTER_FIELDS:
            if filters.get(f):
                cond = {f: {"$in": list(filters[f])}}
                conds.append({"$or": [cond, {f: ""}]} if f in SOFT_FIELDS else cond)
        if filters.get("year_min"):
            conds.append({"$or": [{"year": {"$gte": int(filters["year_min"])}}, {"year": 0}]})
        if filters.get("year_max"):
            conds.append({"$or": [{"year": {"$lte": int(filters["year_max"])}}, {"year": 0}]})
        if filters.get("latest_only"):
            conds.append({"is_latest": True})
        return None if not conds else conds[0] if len(conds) == 1 else {"$and": conds}

    def dense(
        self, query: str, k: int, filters: dict | None = None, store: str = "faiss", faiss_kind: str = "flat"
    ) -> list[tuple[int, float]]:
        if not self.ids:
            return []
        q = embed_query(self.model, query)
        if store == "chroma":
            res = self.chroma().query(
                query_embeddings=[q],
                n_results=min(k, len(self.ids)),
                where=self.chroma_where(filters),
                include=["distances"],
            )
            return [
                (self._pos[cid], 1.0 - dist)
                for cid, dist in zip(res["ids"][0], res["distances"][0], strict=True)
            ]
        import faiss

        ix = self.faiss_index(faiss_kind)
        m = self.mask(filters)
        params = None
        if m is not None:
            allowed = np.nonzero(m)[0].astype(np.int64)
            if not len(allowed):
                return []
            sel = faiss.IDSelectorBatch(allowed)
            params = (
                faiss.SearchParametersHNSW(sel=sel, efSearch=max(64, 2 * k))
                if faiss_kind == "hnsw"
                else faiss.SearchParameters(sel=sel)
            )
        elif faiss_kind == "hnsw":
            params = faiss.SearchParametersHNSW(efSearch=max(64, 2 * k))
        scores, idx = ix.search(q[None, :], min(k, len(self.ids)), params=params)
        return [(int(i), float(s)) for i, s in zip(idx[0], scores[0], strict=True) if i >= 0]

    def lexical(self, query: str, k: int, filters: dict | None = None) -> list[tuple[int, float]]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        m = self.mask(filters)
        if m is not None:
            scores = np.where(m, scores, -np.inf)
        top = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in top if np.isfinite(scores[i]) and scores[i] > 0]

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        k: int = 30,
        filters: dict | None = None,
        store: str = "faiss",
        faiss_kind: str = "flat",
        lexical_query: str | None = None,
    ) -> list[Hit]:
        hits: dict[int, Hit] = {}
        if mode in ("dense", "hybrid"):
            for rank, (i, s) in enumerate(self.dense(query, k, filters, store, faiss_kind), start=1):
                h = hits.setdefault(i, Hit(i, self.ids[i]))
                h.dense, h.dense_rank = s, rank
                h.fused += 1 / (RRF_K + rank)
        if mode in ("bm25", "hybrid"):
            for rank, (i, s) in enumerate(self.lexical(lexical_query or query, k, filters), start=1):
                h = hits.setdefault(i, Hit(i, self.ids[i]))
                h.bm25, h.bm25_rank = s, rank
                h.fused += 1 / (RRF_K + rank)
        out = sorted(hits.values(), key=lambda h: -h.fused)[:k]
        for h in out:
            h.meta = self.meta[h.idx]
        return out


@lru_cache(maxsize=6)
def _get(strategy: str, model: str, collections: tuple[str, ...], version: str) -> Index:
    return Index(strategy, model, collections)


def get_index(strategy: str, model: str, collections=("engineering",)) -> Index:
    return _get(strategy, model, tuple(sorted(collections)), index_version())


class HybridRetriever(BaseRetriever):
    """The hybrid index as a LangChain retriever: documents carry chunk ids and dense / BM25 / RRF scores."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    index: Index
    mode: str = "hybrid"
    k: int = 30
    filters: dict | None = None
    store: str = "faiss"
    faiss_kind: str = "flat"

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[LCDocument]:
        hits = self.index.search(query, self.mode, self.k, self.filters, self.store, self.faiss_kind)
        return [
            LCDocument(
                page_content=self.index.chunks[h.idx].text,
                metadata={
                    **h.meta,
                    "chunk_id": h.chunk_id,
                    "idx": h.idx,
                    "dense": h.dense,
                    "dense_rank": h.dense_rank,
                    "bm25": h.bm25,
                    "bm25_rank": h.bm25_rank,
                    "fused": h.fused,
                },
            )
            for h in hits
        ]


def hits_from_documents(docs: list[LCDocument]) -> list[Hit]:
    return [
        Hit(
            d.metadata["idx"],
            d.metadata["chunk_id"],
            d.metadata["dense"],
            d.metadata["dense_rank"],
            d.metadata["bm25"],
            d.metadata["bm25_rank"],
            d.metadata["fused"],
            meta={
                k: v
                for k, v in d.metadata.items()
                if k not in ("idx", "chunk_id", "dense", "dense_rank", "bm25", "bm25_rank", "fused")
            },
        )
        for d in docs
    ]
