"""Ingestion: file -> layout elements -> 4 chunkings + entities + structured FMEA rows -> SQLite -> indexes.

Incremental: a document is re-processed only when its SHA-256 changes; embeddings are cached by text hash,
so re-indexing only embeds new chunks.
"""

import hashlib
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from sqlmodel import delete

from yokoten.config import load_runtime, settings
from yokoten.db import Chunk, Document, Figure, FmeaItem, init_db, now, select, session
from yokoten.ingest import entities
from yokoten.ingest.chunking import STRATEGIES, chunk
from yokoten.ingest.loaders import EngineeringDocLoader

REPORT = settings.var_dir / "ingestion_report.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(p: Path) -> str:
    return os.path.relpath(p, settings.var_dir).replace("\\", "/")


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _fmea_rows(doc: Document, lc_docs) -> list[FmeaItem]:
    rows = []
    for d in lc_docs:
        v = d.metadata.get("values")
        if not v or "Failure mode" not in v:
            continue
        rows.append(
            FmeaItem(
                doc_id=doc.doc_id,
                revision=doc.revision,
                is_latest=doc.is_latest,
                fmea_type=doc.doc_type,
                component=doc.component,
                plant=doc.plant,
                item_id=str(v.get("ID", "")),
                item=str(v.get("Item / Function", v.get("Process step", ""))),
                failure_mode=str(v["Failure mode"]),
                effect=str(v.get("Effect", "")),
                cause=str(v.get("Cause", "")),
                severity=_int(v.get("S")) or 0,
                occurrence=_int(v.get("O")) or 0,
                detection=_int(v.get("D")) or 0,
                action_priority=str(v.get("AP", "")),
                recommended_action=str(v.get("Recommended action", "")),
                status=str(v.get("Status", "")),
                revised_occurrence=_int(v.get("Revised O")),
                revised_detection=_int(v.get("Revised D")),
                revised_action_priority=v.get("Revised AP") or None,
            )
        )
    return rows


def ingest_file(
    path: Path,
    meta: dict,
    *,
    collection: str = "engineering",
    source: str = "corpus",
    ocr_engine: str = "auto",
    ner: bool = True,
    force: bool = False,
) -> tuple[Document, bool]:
    """Returns (document, processed) - processed is False when the file was unchanged and skipped."""
    t0 = time.perf_counter()
    digest = sha256(path)
    rev = meta.get("revision") or "A"
    rev_key = f"{meta['doc_id']}@{rev}"
    with session() as s:
        doc = s.get(Document, rev_key)
        if doc and doc.sha256 == digest and doc.status == "ready" and not force:
            return doc, False
        fields = {
            k: meta.get(k)
            for k in (
                "title",
                "doc_type",
                "year",
                "date",
                "product_line",
                "component",
                "project",
                "plant",
                "supersedes",
                "superseded_by",
                "author",
            )
        }
        fields["classification"] = meta.get("classification") or "internal"
        doc = doc or Document(
            rev_key=rev_key,
            doc_id=meta["doc_id"],
            title=meta.get("title") or path.name,
            doc_type=meta.get("doc_type") or "other",
            format=path.suffix.lstrip(".").lower(),
            file=meta["file"],
        )
        for k, v in fields.items():
            if v is not None:
                setattr(doc, k, v)
        doc.suppliers = meta.get("suppliers") or []
        doc.part_numbers = meta.get("part_numbers") or []
        doc.revision, doc.collection, doc.source, doc.file = rev, collection, source, meta["file"]
        doc.status, doc.error, doc.sha256, doc.updated_at = "processing", None, digest, now()
        s.add(doc)
        s.commit()
    try:
        loader = EngineeringDocLoader(path, {"doc_id": doc.doc_id, "rev_key": rev_key}, ocr_engine=ocr_engine)
        lc_docs = loader.load()
        parsed = loader.parsed
        t_parse = time.perf_counter()
        text = "\n".join(d.page_content for d in lc_docs)
        extra: dict = {"entities": entities.regex_entities(text)}
        if parsed.ocr:
            f = parsed.ocr["fields"]
            extra["ocr"] = {k: parsed.ocr[k] for k in ("engine", "confidence", "angle", "steps", "fields")}
            doc.ocr_engine, doc.ocr_confidence = parsed.ocr["engine"], parsed.ocr["confidence"]
            if part := f.get("part_number"):
                doc.part_numbers = [part]
                comp = part.split("-")[0]
                if comp in entities.glossary()["components"]:
                    doc.component = comp
                    doc.product_line = entities.glossary()["components"][comp]["line"]
            if f.get("supplier"):
                doc.suppliers = [f["supplier"]]
            if f.get("plant") and (p := entities.plants_in(f["plant"])):
                doc.plant = p[0]
            if f.get("date") and not doc.year:
                doc.year = _int(f["date"][:4])
        if source == "upload":
            inferred = entities.infer_metadata(text, path.name)
            for k, v in inferred.items():
                if v and (not getattr(doc, k, None) or (k == "doc_type" and doc.doc_type == "other")):
                    setattr(doc, k, v)
            if not doc.title or doc.title == path.name:
                first = next((d.page_content for d in lc_docs if d.metadata["kind"] == "heading"), None)
                doc.title = (first or path.stem)[:200]
        if ner:
            extra["organisations"] = entities.organisations(text)
        t_ner = time.perf_counter()
        with session() as s:
            for model in (Chunk, Figure):
                s.exec(delete(model).where(model.rev_key == rev_key))
            s.exec(delete(FmeaItem).where(FmeaItem.doc_id == doc.doc_id, FmeaItem.revision == doc.revision))
            counts = {}
            for strategy in STRATEGIES:
                outs = chunk(lc_docs, strategy)
                counts[strategy] = sum(1 for o in outs if o.indexed)
                for o in outs:
                    s.add(
                        Chunk(
                            id=f"{rev_key}:{strategy}:{o.idx}",
                            rev_key=rev_key,
                            doc_id=doc.doc_id,
                            strategy=strategy,
                            idx=o.idx,
                            kind=o.kind,
                            section=o.section,
                            text=o.text,
                            page=o.page,
                            bboxes=o.bboxes,
                            parent_id=f"{rev_key}:{strategy}:{o.parent_idx}"
                            if o.parent_idx is not None
                            else None,
                            entities=entities.regex_entities(o.text),
                        )
                    )
            for i, fig in enumerate(parsed.figures):
                s.add(
                    Figure(
                        id=f"{rev_key}:fig{i + 1}",
                        rev_key=rev_key,
                        doc_id=doc.doc_id,
                        page=fig["page"],
                        bbox=fig["bbox"],
                        caption=fig["caption"],
                        path=_rel(fig["path"]),
                    )
                )
            if doc.doc_type in ("dfmea", "pfmea"):
                s.add_all(_fmea_rows(doc, lc_docs))
            t_end = time.perf_counter()
            extra["chunks"] = counts
            extra["timings"] = {
                "parse_s": round(t_parse - t0, 2),
                "ner_s": round(t_ner - t_parse, 2),
                "chunk_store_s": round(t_end - t_ner, 2),
                "total_s": round(t_end - t0, 2),
            }
            extra["figures"] = len(parsed.figures)
            doc.extra = extra
            doc.n_pages = parsed.n_pages
            doc.n_chunks = counts[load_runtime().chunking]
            doc.status, doc.updated_at = "ready", now()
            s.add(doc)
            s.commit()
        return doc, True
    except Exception as e:  # keep the error visible in the library instead of failing the whole batch
        with session() as s:
            doc = s.get(Document, rev_key)
            doc.status, doc.error = "error", f"{type(e).__name__}: {e}"
            s.add(doc)
            s.commit()
        raise


_REV = re.compile(r"^[A-Z]{1,2}$")


def update_latest_flags() -> None:
    """Revision awareness: only the highest revision of each document id is 'latest'."""
    with session() as s:
        docs = s.exec(select(Document)).all()
        best: dict[str, str] = {}
        for d in docs:
            r = d.revision if _REV.match(d.revision) else "A"
            if d.doc_id not in best or (len(r), r) > (len(best[d.doc_id]), best[d.doc_id]):
                best[d.doc_id] = r
        for d in docs:
            latest = d.revision == best[d.doc_id]
            if d.is_latest != latest:
                d.is_latest = latest
                s.add(d)
        for row in s.exec(select(FmeaItem)).all():
            row.is_latest = best.get(row.doc_id) == row.revision
            s.add(row)
        s.commit()


def ingest_corpus(
    corpus_dir: Path | None = None,
    *,
    collection: str = "engineering",
    ocr_engine: str = "auto",
    ner: bool = True,
    force: bool = False,
    log=print,
) -> dict:
    from yokoten.retrieval.index import bump_index_version, get_index

    init_db()
    corpus_dir = corpus_dir or settings.corpus_dir
    manifest = json.loads((corpus_dir / "manifest.json").read_text("utf-8"))["documents"]
    t0 = time.perf_counter()
    processed, errors = 0, []
    for i, meta in enumerate(manifest, start=1):
        try:
            doc, did = ingest_file(
                corpus_dir / meta["file"],
                meta,
                collection=collection,
                source="corpus",
                ocr_engine=ocr_engine,
                ner=ner,
                force=force,
            )
            processed += did
            if did:
                log(
                    f"[{i}/{len(manifest)}] {doc.rev_key:28s} {doc.format:4s} {doc.extra['timings']['total_s']:6.2f}s "
                    f"chunks={doc.extra['chunks']}"
                )
        except Exception as e:
            errors.append({"doc_id": meta["doc_id"], "error": f"{type(e).__name__}: {e}"})
            log(f"[{i}/{len(manifest)}] ERROR {meta['doc_id']}: {e}")
    keep = {f"{m['doc_id']}@{m.get('revision') or 'A'}" for m in manifest}
    with session() as s:
        stale = [
            d
            for d in s.exec(
                select(Document).where(Document.source == "corpus", Document.collection == collection)
            ).all()
            if d.rev_key not in keep
        ]
        for d in stale:
            for model in (Chunk, Figure):
                s.exec(delete(model).where(model.rev_key == d.rev_key))
            s.exec(delete(FmeaItem).where(FmeaItem.doc_id == d.doc_id, FmeaItem.revision == d.revision))
            s.delete(d)
        s.commit()
    update_latest_flags()
    t_docs = time.perf_counter()
    if processed or stale or force:
        bump_index_version()
    cfg = load_runtime()
    index = get_index(cfg.chunking, cfg.embedding_model)
    index.faiss_index("flat")
    index.chroma()
    report = build_report()
    report["run"] = {
        "processed": processed,
        "skipped": len(manifest) - processed - len(errors),
        "removed": len(stale),
        "errors": errors,
        "documents_s": round(t_docs - t0, 1),
        "index_s": round(time.perf_counter() - t_docs, 1),
        "index": index.stats,
    }
    REPORT.write_text(json.dumps(report, indent=2), "utf-8")
    return report


def build_report() -> dict:
    with session() as s:
        docs = s.exec(select(Document)).all()
        chunks = s.exec(select(Chunk.strategy, Chunk.kind)).all()
        n_fmea = len(s.exec(select(FmeaItem.id)).all())
        n_fig = len(s.exec(select(Figure.id)).all())
    ocr = [d for d in docs if d.ocr_engine]
    return {
        "documents": len(docs),
        "by_status": dict(Counter(d.status for d in docs)),
        "by_type": dict(Counter(d.doc_type for d in docs)),
        "by_format": dict(Counter(d.format for d in docs)),
        "by_collection": dict(Counter(d.collection for d in docs)),
        "chunks": {st: sum(1 for c in chunks if c[0] == st and c[1] != "parent") for st in STRATEGIES},
        "parent_sections": sum(1 for c in chunks if c[1] == "parent"),
        "figures": n_fig,
        "fmea_rows": n_fmea,
        "ocr": {
            "documents": len(ocr),
            "engines": dict(Counter(d.ocr_engine for d in ocr)),
            "mean_confidence": round(sum(d.ocr_confidence for d in ocr) / len(ocr), 3) if ocr else None,
        },
        "superseded_revisions": sum(1 for d in docs if not d.is_latest),
    }
