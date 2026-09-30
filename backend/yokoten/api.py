"""FastAPI app: REST + SSE. Run: uv run uvicorn yokoten.api:app --reload"""

import re
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from sqlmodel import delete, func

from yokoten import __version__
from yokoten.config import RuntimeConfig, device, load_runtime, save_runtime, settings
from yokoten.db import (
    ChatMessage,
    ChatSession,
    Chunk,
    Document,
    Feedback,
    Figure,
    FmeaItem,
    Trace,
    init_db,
    select,
    session,
)
from yokoten.domain import DEFAULT_ROLE, DOC_TYPE_LABEL, ROLE_ACCESS
from yokoten.ingest.loaders import SUPPORTED

init_db()
BOOTSTRAP = {"running": False, "error": None}


def _bootstrap() -> None:
    """First start with an empty database: generate the demo corpus (if missing) and ingest it."""
    from yokoten.config import ROOT
    from yokoten.ingest.pipeline import ingest_corpus

    BOOTSTRAP["running"] = True
    try:
        if not (settings.corpus_dir / "manifest.json").exists():
            from yokoten.datagen import generate

            generate(settings.corpus_dir, ROOT / "eval" / "golden.jsonl")
        ingest_corpus(log=lambda m: None)
    except Exception as e:  # visible in /api/health
        BOOTSTRAP["error"] = f"{type(e).__name__}: {e}"
    finally:
        BOOTSTRAP["running"] = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    with session() as s:
        empty = s.exec(select(func.count()).select_from(Document)).one() == 0
    if settings.auto_ingest and empty:
        threading.Thread(target=_bootstrap, daemon=True).start()
    yield


app = FastAPI(
    title="Yokoten API",
    version=__version__,
    description="Engineering lessons-learned copilot",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOAD_DIR = settings.var_dir / "uploads"

# ------------------------------------------------------------------ demo-mode rate limiting (per client IP)
_hits: dict[str, deque] = defaultdict(deque)
_rl_lock = threading.Lock()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if settings.demo_mode and request.method == "POST":
        ip = request.client.host if request.client else "?"
        now_t = time.time()
        with _rl_lock:
            q = _hits[ip]
            while q and now_t - q[0] > 60:
                q.popleft()
            if len(q) >= settings.rate_limit_per_min:
                return JSONResponse({"detail": "Rate limit reached - please wait a minute."}, status_code=429)
            q.append(now_t)
    return await call_next(request)


def role_of(x_role: str | None) -> str:
    return x_role if x_role in ROLE_ACCESS else DEFAULT_ROLE


def _writable() -> None:
    if settings.demo_mode:
        raise HTTPException(403, "This public demo is read-only.")


RoleHeader = Annotated[str | None, Header(alias="X-Role")]


# ------------------------------------------------------------------ health / config
@app.get("/api/health")
def health() -> dict:
    from yokoten.rag import llm

    with session() as s:
        n_docs = s.exec(select(func.count()).select_from(Document)).one()
        n_ready = s.exec(select(func.count()).select_from(Document).where(Document.status == "ready")).one()
    return {
        "status": "ok",
        "version": __version__,
        "demo_mode": settings.demo_mode,
        "documents": n_docs,
        "ready": n_ready,
        "bootstrapping": BOOTSTRAP["running"],
        "bootstrap_error": BOOTSTRAP["error"],
        "providers": llm.available(),
        "device": device(),
    }


class ConfigOut(BaseModel):
    config: RuntimeConfig
    options: dict


@app.get("/api/config")
def get_config() -> ConfigOut:
    from yokoten.rag import llm
    from yokoten.retrieval.embeddings import EMBED_MODELS

    avail = llm.available()
    return ConfigOut(
        config=load_runtime(),
        options={
            "providers": {
                p: {
                    "available": avail[p],
                    "default": llm.PROVIDERS[p]["default"],
                    "models": llm.list_models(p) if avail[p] else [],
                }
                for p in llm.ORDER
            },
            "embedding_models": list(EMBED_MODELS),
            "chunking": ["fixed", "recursive", "structure", "parent_child"],
            "vector_stores": ["faiss", "chroma"],
            "faiss_index": ["flat", "hnsw"],
            "retrieval_modes": ["dense", "bm25", "hybrid"],
            "prompt_versions": sorted(
                p.stem.split("_")[1] for p in (Path(__file__).parents[1] / "prompts").glob("answer_v*.md")
            ),
            "roles": list(ROLE_ACCESS),
        },
    )


@app.put("/api/config")
def put_config(cfg: RuntimeConfig) -> RuntimeConfig:
    _writable()
    save_runtime(cfg)
    return cfg


# ------------------------------------------------------------------ chat (SSE)
class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    history: list[dict] | None = None
    config: dict | None = None  # per-request overrides (e.g. from the settings drawer)


def _history(session_id: str) -> list[dict]:
    with session() as s:
        msgs = s.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc())
            .limit(6)
        ).all()
    return [{"role": m.role, "content": m.content} for m in reversed(msgs)]


@app.post("/api/chat", response_class=EventSourceResponse)
def chat(body: ChatIn, x_role: RoleHeader = None) -> Iterator[ServerSentEvent]:
    from yokoten.rag.pipeline import answer

    role = role_of(x_role)
    cfg = load_runtime().model_copy(update=body.config or {})
    sid = body.session_id or uuid.uuid4().hex[:12]
    with session() as s:
        if not s.get(ChatSession, sid):
            s.add(ChatSession(id=sid, title=body.question[:80], role=role))
            s.commit()
    history = body.history if body.history is not None else _history(sid)
    yield ServerSentEvent(event="session", data={"session_id": sid})
    try:
        for ev in answer(body.question, history, cfg, role, session_id=sid):
            if ev["event"] == "done":
                with session() as s:
                    s.add(ChatMessage(session_id=sid, role="user", content=body.question))
                    s.add(
                        ChatMessage(
                            session_id=sid,
                            role="assistant",
                            content=ev["data"]["answer"],
                            trace_id=ev["data"]["trace_id"],
                        )
                    )
                    s.commit()
            yield ServerSentEvent(event=ev["event"], data=ev["data"])
    except Exception as e:  # surface provider/key errors to the UI instead of a broken stream
        yield ServerSentEvent(event="error", data={"message": f"{type(e).__name__}: {e}"})


@app.get("/api/sessions")
def list_sessions(x_role: RoleHeader = None) -> list[ChatSession]:
    with session() as s:
        return list(s.exec(select(ChatSession).order_by(ChatSession.created_at.desc()).limit(50)).all())


@app.get("/api/sessions/{sid}")
def get_session(sid: str) -> list[ChatMessage]:
    with session() as s:
        return list(
            s.exec(select(ChatMessage).where(ChatMessage.session_id == sid).order_by(ChatMessage.id)).all()
        )


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> Trace:
    with session() as s:
        t = s.get(Trace, trace_id)
    if not t:
        raise HTTPException(404, "trace not found")
    return t


class FeedbackIn(BaseModel):
    trace_id: str
    rating: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=2000)


@app.post("/api/feedback")
def feedback(body: FeedbackIn, x_role: RoleHeader = None) -> Feedback:
    with session() as s:
        if not s.get(Trace, body.trace_id):
            raise HTTPException(404, "trace not found")
        fb = Feedback(trace_id=body.trace_id, rating=body.rating, comment=body.comment, role=role_of(x_role))
        s.add(fb)
        s.commit()
        return fb


# ------------------------------------------------------------------ semantic search
class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    mode: str = "hybrid"
    rerank: bool = True
    k: int = Field(default=20, ge=1, le=50)
    filters: dict = Field(default_factory=dict)


def _highlight_terms(query: str) -> list[str]:
    from yokoten.retrieval.index import STOP

    return sorted(
        {
            t
            for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-./]+", query)
            if t.lower() not in STOP and len(t) > 2
        },
        key=len,
        reverse=True,
    )


@app.post("/api/search")
def search(body: SearchIn, x_role: RoleHeader = None) -> dict:
    from yokoten.rag import models
    from yokoten.rag.query import expand
    from yokoten.retrieval.index import get_index

    cfg = load_runtime()
    t0 = time.perf_counter()
    index = get_index(cfg.chunking, cfg.embedding_model)
    filters = {k: v for k, v in body.filters.items() if v not in (None, "", [])}
    filters["classification"] = ROLE_ACCESS[role_of(x_role)]
    filters.setdefault("collection", cfg.collections)
    expanded, _ = expand(body.query)
    hits = index.search(expanded, body.mode, max(body.k * 2, 30), filters, cfg.vector_store, cfg.faiss_index)
    if body.rerank and hits:
        for h, sc in zip(
            hits, models.rerank_scores(body.query, [index.embed_texts[h.idx] for h in hits]), strict=True
        ):
            h.rerank = sc
        hits.sort(key=lambda h: -h.rerank)
    results, per_doc = [], defaultdict(int)
    for h in hits:
        if per_doc[h.meta["rev_key"]] >= 2 or len(results) >= body.k:
            continue
        per_doc[h.meta["rev_key"]] += 1
        c = index.chunks[h.idx]
        results.append(
            {
                **{
                    k: h.meta[k]
                    for k in (
                        "doc_id",
                        "rev_key",
                        "title",
                        "doc_type",
                        "product_line",
                        "component",
                        "project",
                        "plant",
                        "year",
                        "revision",
                        "is_latest",
                    )
                },
                "doc_type_label": DOC_TYPE_LABEL.get(h.meta["doc_type"], h.meta["doc_type"]),
                "chunk_id": c.id,
                "section": c.section,
                "page": c.page,
                "text": c.text[:700],
                "scores": {
                    "dense": h.dense,
                    "dense_rank": h.dense_rank,
                    "bm25": h.bm25,
                    "bm25_rank": h.bm25_rank,
                    "fused": round(h.fused, 5),
                    "rerank": h.rerank,
                    "relevance": round(models.sigmoid(h.rerank), 3) if h.rerank is not None else None,
                },
            }
        )
    return {
        "query": body.query,
        "expanded": expanded,
        "terms": _highlight_terms(body.query),
        "results": results,
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@app.get("/api/facets")
def facets(x_role: RoleHeader = None) -> dict:
    allowed = ROLE_ACCESS[role_of(x_role)]
    with session() as s:
        docs = s.exec(
            select(Document).where(Document.classification.in_(allowed), Document.status == "ready")
        ).all()
    out: dict = {}
    for f in ("doc_type", "product_line", "component", "project", "plant", "year", "collection"):
        counts: dict = defaultdict(int)
        for d in docs:
            if (v := getattr(d, f)) not in (None, ""):
                counts[v] += 1
        out[f] = sorted(({"value": k, "count": v} for k, v in counts.items()), key=lambda x: str(x["value"]))
    out["doc_type_labels"] = DOC_TYPE_LABEL
    return out


# ------------------------------------------------------------------ document library
def _doc_or_404(rev_key: str, role: str) -> Document:
    with session() as s:
        d = s.get(Document, rev_key)
    if not d or d.classification not in ROLE_ACCESS[role]:
        raise HTTPException(404, "document not found")
    return d


def _file_path(d: Document) -> Path:
    base = (
        UPLOAD_DIR
        if d.source == "upload"
        else settings.data_dir / "public"
        if d.collection == "public_recalls"
        else settings.corpus_dir
    )
    return base / d.file


@app.get("/api/documents")
def list_documents(
    x_role: RoleHeader = None,
    q: str | None = None,
    doc_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=500, le=2000),
) -> list[dict]:
    with session() as s:
        stmt = select(Document).where(Document.classification.in_(ROLE_ACCESS[role_of(x_role)]))
        if doc_type:
            stmt = stmt.where(Document.doc_type == doc_type)
        if status:
            stmt = stmt.where(Document.status == status)
        docs = s.exec(stmt.order_by(Document.doc_id).limit(limit)).all()
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in d.doc_id.lower() or ql in d.title.lower()]
    return [
        {
            **d.model_dump(exclude={"extra"}),
            "doc_type_label": DOC_TYPE_LABEL.get(d.doc_type, d.doc_type),
            "ocr_fields": d.extra.get("ocr", {}).get("fields"),
            "timings": d.extra.get("timings"),
        }
        for d in docs
    ]


@app.get("/api/documents/{rev_key}")
def get_document(rev_key: str, x_role: RoleHeader = None, strategy: str | None = None) -> dict:
    d = _doc_or_404(rev_key, role_of(x_role))
    strategy = strategy or load_runtime().chunking
    with session() as s:
        chunks = s.exec(
            select(Chunk).where(Chunk.rev_key == rev_key, Chunk.strategy == strategy).order_by(Chunk.idx)
        ).all()
        figs = s.exec(select(Figure).where(Figure.rev_key == rev_key)).all()
        revisions = s.exec(
            select(Document.rev_key, Document.revision, Document.is_latest).where(Document.doc_id == d.doc_id)
        ).all()
        fmea = s.exec(
            select(FmeaItem).where(FmeaItem.doc_id == d.doc_id, FmeaItem.revision == d.revision)
        ).all()
    return {
        "document": {**d.model_dump(), "doc_type_label": DOC_TYPE_LABEL.get(d.doc_type, d.doc_type)},
        "chunks": [c.model_dump() for c in chunks],
        "figures": [f.model_dump() for f in figs],
        "revisions": [{"rev_key": r[0], "revision": r[1], "is_latest": r[2]} for r in revisions],
        "fmea_rows": [r.model_dump() for r in fmea],
        "strategy": strategy,
    }


@app.get("/api/documents/{rev_key}/file")
def download(rev_key: str, x_role: RoleHeader = None) -> FileResponse:
    d = _doc_or_404(rev_key, role_of(x_role))
    return FileResponse(_file_path(d), filename=Path(d.file).name)


def _png(data: bytes) -> Response:
    return Response(data, media_type="image/png", headers={"Cache-Control": "max-age=300"})


@app.get("/api/documents/{rev_key}/page/{page}")
def page_image(rev_key: str, page: int, chunk: str | None = None, x_role: RoleHeader = None) -> Response:
    """PDF page rendered server-side, with the cited passage highlighted."""
    import pymupdf

    d = _doc_or_404(rev_key, role_of(x_role))
    if d.format != "pdf":
        raise HTTPException(400, "page rendering is available for PDFs")
    pdf = pymupdf.open(_file_path(d))
    if not 1 <= page <= pdf.page_count:
        raise HTTPException(404, "page out of range")
    pg = pdf[page - 1]
    if chunk:
        with session() as s:
            c = s.get(Chunk, chunk)
        rects = []
        if c:
            for piece in re.split(r"\n+", c.text):
                piece = " ".join(piece.split())[:60]
                if len(piece) >= 12:
                    rects += pg.search_for(piece)
            if not rects:
                rects = [pymupdf.Rect(b[1:]) for b in c.bboxes if b[0] == page]
        for r in rects:
            pg.add_highlight_annot(r)
    return _png(pg.get_pixmap(dpi=110, annots=True).tobytes("png"))


@app.get("/api/documents/{rev_key}/image")
def scan_image(
    rev_key: str, step: str = "deskewed", chunk: str | None = None, x_role: RoleHeader = None
) -> Response:
    """OCR pipeline step image (original / denoised / deskewed / binary), optionally with OCR boxes highlighted."""
    import cv2
    import numpy as np

    d = _doc_or_404(rev_key, role_of(x_role))
    steps = d.extra.get("ocr", {}).get("steps", {})
    if step not in steps:
        raise HTTPException(404, "no such processing step")
    img = cv2.imdecode(np.fromfile(str(settings.var_dir / steps[step]), np.uint8), cv2.IMREAD_COLOR)
    if chunk and step in ("deskewed", "binary"):
        with session() as s:
            c = s.get(Chunk, chunk)
        h, w = img.shape[:2]
        overlay = img.copy()
        for b in c.bboxes if c else []:
            x0, y0, x1, y1 = b[1:]
            cv2.rectangle(
                overlay,
                (int(x0 * w) - 4, int(y0 * h) - 4),
                (int(x1 * w) + 4, int(y1 * h) + 4),
                (0, 215, 255),
                -1,
            )
        img = cv2.addWeighted(overlay, 0.35, img, 0.65, 0)
    return _png(cv2.imencode(".png", img)[1].tobytes())


@app.get("/api/figures/{figure_id}")
def figure(figure_id: str) -> FileResponse:
    with session() as s:
        f = s.get(Figure, figure_id)
    if not f:
        raise HTTPException(404, "figure not found")
    return FileResponse(settings.var_dir / f.path)


def _ingest_upload(path: Path, meta: dict) -> None:
    from yokoten.ingest.pipeline import ingest_file, update_latest_flags
    from yokoten.retrieval.index import bump_index_version

    try:
        ingest_file(path, meta, source="upload", ner=True)
        update_latest_flags()
        bump_index_version()
    except Exception:  # status/error is stored on the document row
        pass


@app.post("/api/documents")
def upload(
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    classification: Annotated[str, Query()] = "internal",
) -> dict:
    _writable()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED:
        raise HTTPException(
            415, f"Unsupported file type {ext or '?'}; allowed: {', '.join(sorted(SUPPORTED))}"
        )
    if classification not in ROLE_ACCESS["admin"]:
        raise HTTPException(400, "invalid classification")
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {settings.max_upload_mb} MB")
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(file.filename).stem)[:60] or "upload"
    doc_id = f"UP-{stem}"
    rel = f"{doc_id}{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / rel).write_bytes(data)
    meta = {
        "doc_id": doc_id,
        "file": rel,
        "title": Path(file.filename).name,
        "classification": classification,
    }
    with session() as s:  # visible immediately as "pending" in the library
        if not s.get(Document, f"{doc_id}@A"):
            s.add(
                Document(
                    rev_key=f"{doc_id}@A",
                    doc_id=doc_id,
                    title=Path(file.filename).name,
                    doc_type="other",
                    format=ext.lstrip("."),
                    file=rel,
                    source="upload",
                    classification=classification,
                )
            )
            s.commit()
    background.add_task(_ingest_upload, UPLOAD_DIR / rel, meta)
    return {"rev_key": f"{doc_id}@A", "status": "pending"}


@app.post("/api/documents/{rev_key}/reindex")
def reindex(rev_key: str, background: BackgroundTasks, x_role: RoleHeader = None) -> dict:
    _writable()
    d = _doc_or_404(rev_key, role_of(x_role))
    meta = {**d.model_dump(), "doc_id": d.doc_id}
    with session() as s:
        row = s.get(Document, rev_key)
        row.status = "pending"
        s.add(row)
        s.commit()

    def run():
        from yokoten.ingest.pipeline import ingest_file
        from yokoten.retrieval.index import bump_index_version

        try:
            ingest_file(_file_path(d), meta, collection=d.collection, source=d.source, force=True)
            bump_index_version()
        except Exception:
            pass

    background.add_task(run)
    return {"rev_key": rev_key, "status": "pending"}


@app.delete("/api/documents/{rev_key}")
def delete_document(rev_key: str, x_role: RoleHeader = None) -> dict:
    _writable()
    from yokoten.ingest.pipeline import update_latest_flags
    from yokoten.retrieval.index import bump_index_version

    d = _doc_or_404(rev_key, role_of(x_role))
    with session() as s:
        for model in (Chunk, Figure):
            s.exec(delete(model).where(model.rev_key == rev_key))
        s.exec(delete(FmeaItem).where(FmeaItem.doc_id == d.doc_id, FmeaItem.revision == d.revision))
        s.delete(s.get(Document, rev_key))
        s.commit()
    if d.source == "upload":
        _file_path(d).unlink(missing_ok=True)
    update_latest_flags()
    bump_index_version()
    return {"deleted": rev_key}


@app.get("/api/ingestion/report")
def ingestion_report() -> dict:
    import json

    p = settings.var_dir / "ingestion_report.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


# ------------------------------------------------------------------ catalog + onboarding digest
@app.get("/api/catalog")
def catalog() -> dict:
    from yokoten.ingest.entities import glossary

    g = glossary()
    return {
        "components": {k: {"name": v["name"], "line": v["line"]} for k, v in g["components"].items()},
        "product_lines": {
            "thermal": "Thermal Systems",
            "powertrain": "Powertrain Components",
            "electrification": "Electrification",
            "body_electronics": "Body Electronics",
        },
        "plants": {k: v[0].title() for k, v in g["plants"].items()},
        "doc_types": DOC_TYPE_LABEL,
        "roles": list(ROLE_ACCESS),
    }


class DigestIn(BaseModel):
    component: str | None = None
    product_line: str | None = None


def _digest(body: DigestIn, role: str) -> dict:
    from yokoten.rag.onboarding import digest

    if not (body.component or body.product_line):
        raise HTTPException(400, "choose a component or a product line")
    return digest(body.component, body.product_line, role)


@app.post("/api/onboarding")
def onboarding(body: DigestIn, x_role: RoleHeader = None) -> dict:
    return _digest(body, role_of(x_role))


@app.post("/api/onboarding/summary")
def onboarding_summary(body: DigestIn, x_role: RoleHeader = None) -> dict:
    from yokoten.rag.onboarding import summary

    cfg = load_runtime()
    return summary(_digest(body, role_of(x_role)), cfg.llm_provider, cfg.llm_model)


# ------------------------------------------------------------------ evaluation results
def _latest_eval() -> dict:
    import json

    from yokoten.evaluation.harness import RESULTS

    p = RESULTS / "latest.json"
    if not p.exists():
        raise HTTPException(404, "no evaluation run yet")
    return json.loads(p.read_text("utf-8"))


@app.get("/api/eval/latest")
def eval_latest() -> dict:
    run = _latest_eval()
    run["retrieval"].pop("rows", None)
    for g in run["generation"]["configs"]:
        g.pop("rows", None)
    return run


@app.get("/api/eval/summary")
def eval_summary() -> dict:
    run = _latest_eval()
    c = run["config"]
    return {
        "run_id": run["run_id"],
        "created_at": run["created_at"],
        "headline": run["headline"],
        "split": run["split"],
        "config": f"{c['retrieval_mode']} · {c['chunking']} · "
        f"{c['embedding_model'].split('/')[-1]} · rerank {'on' if c['reranker'] else 'off'}",
    }


@app.get("/api/eval/runs")
def eval_runs() -> list[dict]:
    from yokoten.db import EvalRun

    with session() as s:
        return [r.model_dump() for r in s.exec(select(EvalRun).order_by(EvalRun.created_at.desc())).all()]


# ------------------------------------------------------------------ SME verification loop + feedback analytics
SME_ROLES = ("quality_sme", "admin")


class VerifyIn(BaseModel):
    trace_id: str
    status: str = Field(pattern="^(verified|corrected)$")
    corrected_answer: str | None = Field(default=None, max_length=4000)
    note: str = Field(default="", max_length=1000)


@app.post("/api/verify")
def verify_answer(body: VerifyIn, x_role: RoleHeader = None) -> dict:
    from yokoten.db import VerifiedAnswer

    _writable()
    role = role_of(x_role)
    if role not in SME_ROLES:
        raise HTTPException(403, "Only quality SMEs and admins can verify answers.")
    with session() as s:
        t = s.get(Trace, body.trace_id)
        if not t:
            raise HTTPException(404, "trace not found")
        if body.status == "corrected" and not (body.corrected_answer or "").strip():
            raise HTTPException(400, "a corrected answer is required")
        v = VerifiedAnswer(
            trace_id=t.id,
            question=t.question,
            standalone=t.standalone or t.question,
            answer=(body.corrected_answer or t.answer).strip(),
            status=body.status,
            note=body.note,
            role=role,
        )
        s.add(v)
        s.commit()
        return v.model_dump()


@app.get("/api/verified")
def list_verified() -> list[dict]:
    from yokoten.db import VerifiedAnswer

    with session() as s:
        return [
            v.model_dump() for v in s.exec(select(VerifiedAnswer).order_by(VerifiedAnswer.id.desc())).all()
        ]


@app.get("/api/feedback/analytics")
def feedback_analytics() -> dict:
    from yokoten.db import VerifiedAnswer

    with session() as s:
        fbs = s.exec(select(Feedback)).all()
        traces = {t.id: t for t in s.exec(select(Trace)).all()}
        n_verified = len(s.exec(select(VerifiedAnswer.id)).all())
    by_day: dict = defaultdict(lambda: {"up": 0, "down": 0})
    by_intent: dict = defaultdict(lambda: {"up": 0, "down": 0})
    conf = {"up": [], "down": []}
    negative = []
    for f in fbs:
        key = "up" if f.rating > 0 else "down"
        t = traces.get(f.trace_id)
        by_day[f.created_at.date().isoformat()][key] += 1
        if t:
            by_intent[t.intent or "unknown"][key] += 1
            if t.confidence is not None:
                conf[key].append(t.confidence)
            if key == "down":
                negative.append(
                    {
                        "trace_id": t.id,
                        "question": t.question,
                        "answer": t.answer[:300],
                        "comment": f.comment,
                        "created_at": f.created_at.isoformat(),
                    }
                )
    return {
        "total": len(fbs),
        "up": sum(1 for f in fbs if f.rating > 0),
        "down": sum(1 for f in fbs if f.rating < 0),
        "questions_answered": len(traces),
        "abstained": sum(1 for t in traces.values() if t.abstained),
        "verified_answers": n_verified,
        "mean_confidence": {k: (sum(v) / len(v) if v else None) for k, v in conf.items()},
        "by_day": [{"day": d, **v} for d, v in sorted(by_day.items())],
        "by_intent": [{"intent": k, **v} for k, v in sorted(by_intent.items())],
        "recent_negative": sorted(negative, key=lambda x: x["created_at"], reverse=True)[:10],
    }
