"""The RAG pipeline. Every step is timed and recorded in the trace shown by the explainability panel.

condense -> expand acronyms -> extract filters -> intent route -> hybrid retrieval (+role filter) -> rerank ->
relevance gate -> small-to-big + dedup + revision awareness -> versioned prompt -> streamed answer ->
NLI check per sentence -> confidence -> trace
"""

import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field

from yokoten.config import RuntimeConfig, load_runtime
from yokoten.db import Chunk, Document, Trace, select, session
from yokoten.domain import DEFAULT_ROLE, DOC_TYPE_LABEL, ROLE_ACCESS
from yokoten.rag import llm, models
from yokoten.rag import sql as sqlroute
from yokoten.rag import verified as verified_mod
from yokoten.rag.query import condense, expand, extract_filters, load_prompt
from yokoten.retrieval.index import Hit, HybridRetriever, Index, get_index, hits_from_documents

ABSTAIN = "I could not find this in the knowledge base."
FOLLOWUP = "follow-up questions:"
MAX_CONTEXT_CHARS = 9000
NLI_SUPPORT = 0.5


@dataclass
class Source:
    n: int
    chunk_id: str
    doc_id: str
    rev_key: str
    title: str
    doc_type: str
    revision: str
    is_latest: bool
    superseded_by: str | None
    format: str
    page: int | None
    section: str
    bboxes: list
    snippet: str  # the retrieved (child) text - highlighted in the viewer
    text: str  # what the LLM sees (parent section for small-to-big)
    scores: dict = field(default_factory=dict)


@dataclass
class Retrieval:
    question: str
    standalone: str
    condense_method: str
    expanded: str
    expansions: list
    filters: dict
    filters_relaxed: bool
    intent: str
    intent_detail: dict
    hits: list[Hit]
    gate: float
    passed_gate: bool
    index: Index
    steps: list


class _Steps(list):
    @contextmanager
    def step(self, name: str, **data):
        t = time.perf_counter()
        rec = {"name": name, **data}
        yield rec
        rec["ms"] = round((time.perf_counter() - t) * 1000, 1)
        self.append(rec)


def _hit_row(h: Hit, index: Index) -> dict:
    c = index.chunks[h.idx]
    return {
        "chunk_id": h.chunk_id,
        "doc_id": h.meta["doc_id"],
        "title": h.meta["title"],
        "revision": h.meta["revision"],
        "section": c.section,
        "page": c.page,
        "kind": c.kind,
        "dense": None if h.dense is None else round(h.dense, 4),
        "dense_rank": h.dense_rank,
        "bm25": None if h.bm25 is None else round(h.bm25, 3),
        "bm25_rank": h.bm25_rank,
        "fused": round(h.fused, 5),
        "rerank": None if h.rerank is None else round(h.rerank, 3),
        "snippet": c.text[:240],
    }


def retrieve(
    question: str,
    history: list[dict] | None = None,
    cfg: RuntimeConfig | None = None,
    role: str = DEFAULT_ROLE,
    llm_for_condense: tuple[str, str] | None = None,
) -> Retrieval:
    cfg = cfg or load_runtime()
    steps = _Steps()
    history = history or []
    with steps.step("condense") as rec:
        if cfg.query_rewrite:
            standalone, method = condense(question, history, *(llm_for_condense or (None, None)))
        else:
            standalone, method = (question, "disabled")
        rec.update(method=method, output=standalone)
    with steps.step("expand") as rec:
        expanded, added = expand(standalone) if cfg.query_rewrite else (standalone, [])
        rec.update(added=added)
    with steps.step("filters") as rec:
        filters = extract_filters(standalone) if cfg.use_filters else {}
        rec.update(filters=dict(filters))
    with steps.step("intent") as rec:
        intent, detail = models.classify_intent(standalone)
        rec.update(intent=intent, **detail)
    index = get_index(cfg.chunking, cfg.embedding_model)
    base = {"classification": ROLE_ACCESS.get(role, ROLE_ACCESS[DEFAULT_ROLE]), "collection": cfg.collections}
    with steps.step(
        "retrieve", mode=cfg.retrieval_mode, store=cfg.vector_store, faiss=cfg.faiss_index
    ) as rec:
        retriever = HybridRetriever(
            index=index,
            mode=cfg.retrieval_mode,
            k=cfg.candidates,
            filters={**base, **filters},
            store=cfg.vector_store,
            faiss_kind=cfg.faiss_index,
        )
        hits = hits_from_documents(retriever.invoke(expanded))
        relaxed = False
        if not hits and filters:  # over-specific filters: retry with access filters only
            retriever.filters = base
            hits = hits_from_documents(retriever.invoke(expanded))
            relaxed = True
        rec.update(candidates=len(hits), filters_relaxed=relaxed)
    with steps.step("rerank", enabled=cfg.reranker) as rec:
        if cfg.reranker and hits:
            scores = models.rerank_scores(standalone, [index.embed_texts[h.idx] for h in hits])
            for h, s in zip(hits, scores, strict=True):
                h.rerank = s
            hits.sort(key=lambda h: -h.rerank)
        rec.update(top=hits[0].chunk_id if hits else None)
    with steps.step("gate") as rec:
        if not hits:
            gate = 0.0
        elif cfg.reranker:
            gate = models.sigmoid(hits[0].rerank)
        else:
            gate = max((h.dense or 0.0) for h in hits) if cfg.retrieval_mode != "bm25" else 1.0
        threshold = cfg.abstain_threshold if cfg.reranker else cfg.abstain_threshold_dense
        passed = bool(hits) and gate >= threshold
        rec.update(score=round(gate, 4), threshold=threshold, passed=passed)
    return Retrieval(
        question,
        standalone,
        method,
        expanded,
        added,
        filters,
        relaxed,
        intent,
        detail,
        hits,
        gate,
        passed,
        index,
        steps,
    )


def build_context(r: Retrieval, cfg: RuntimeConfig, verified: dict | None = None) -> list[Source]:
    """Small-to-big (child -> parent section), dedup, revision awareness (add the latest revision when only a
    superseded one was retrieved), numbered passages."""
    index = r.index
    chosen: list[tuple[Hit, Chunk, str]] = []
    seen: set[str] = set()
    with session() as s:
        for h in r.hits:
            if len(chosen) >= cfg.top_k:
                break
            c = index.chunks[h.idx]
            parent = s.get(Chunk, c.parent_id) if c.parent_id else None
            key = parent.id if parent else c.id
            if key in seen:
                continue
            seen.add(key)
            chosen.append((h, c, parent.text if parent else c.text))
        docs = {
            d.rev_key: d
            for d in s.exec(
                select(Document).where(Document.rev_key.in_([h.meta["rev_key"] for h, _, _ in chosen]))
            ).all()
        }
        # revision awareness: if a superseded revision is in context but its latest revision is not, add the latest
        extra = []
        present = {d.doc_id for d in docs.values() if d.is_latest}
        for d in list(docs.values()):
            if not d.is_latest and d.doc_id not in present:
                latest = s.exec(
                    select(Document).where(Document.doc_id == d.doc_id, Document.is_latest)
                ).first()
                if not latest:
                    continue
                cands = s.exec(
                    select(Chunk).where(
                        Chunk.rev_key == latest.rev_key,
                        Chunk.strategy == cfg.chunking,
                        Chunk.kind != "parent",
                    )
                ).all()
                if cands:
                    scores = models.rerank_scores(r.standalone, [c.text for c in cands])
                    best = cands[max(range(len(cands)), key=scores.__getitem__)]
                    parent = s.get(Chunk, best.parent_id) if best.parent_id else None
                    extra.append((best, parent.text if parent else best.text, latest))
                    docs[latest.rev_key] = latest
                    present.add(d.doc_id)
    sources: list[Source] = []
    total = 0

    def add(c: Chunk, text: str, d: Document, scores: dict):
        nonlocal total
        if total + len(text) > MAX_CONTEXT_CHARS and sources:
            return
        total += len(text)
        sources.append(
            Source(
                n=len(sources) + 1,
                chunk_id=c.id,
                doc_id=d.doc_id,
                rev_key=d.rev_key,
                title=d.title,
                doc_type=d.doc_type,
                revision=d.revision,
                is_latest=d.is_latest,
                superseded_by=d.superseded_by,
                format=d.format,
                page=c.page,
                section=c.section,
                bboxes=c.bboxes,
                snippet=c.text,
                text=text,
                scores=scores,
            )
        )

    if verified:  # SME-verified answer to a near-identical question goes first
        sources.append(
            Source(
                n=1,
                chunk_id=f"verified:{verified['id']}",
                doc_id=f"SME-VERIFIED-{verified['id']}",
                rev_key="",
                title=f"SME-{verified['status']} answer to: {verified['question']}",
                doc_type="verified",
                revision="-",
                is_latest=True,
                superseded_by=None,
                format="verified",
                page=None,
                section="",
                bboxes=[],
                snippet=verified["answer"],
                text=verified["answer"],
                scores={"similarity": verified["similarity"]},
            )
        )
        total += len(verified["answer"])
    for h, c, text in chosen:
        add(
            c,
            text,
            docs[h.meta["rev_key"]],
            {"dense": h.dense, "bm25": h.bm25, "fused": h.fused, "rerank": h.rerank},
        )
    for c, text, d in extra:
        add(c, text, d, {"added_for": "latest revision"})
    return sources


def format_context(sources: list[Source]) -> str:
    blocks = []
    for s in sources:
        if s.doc_type in ("verified", "sql"):
            label = (
                "SME-VERIFIED ANSWER (checked by a quality expert)" if s.doc_type == "verified" else s.title
            )
            blocks.append(f"[{s.n}] {label}\n{s.text}")
            continue
        status = "LATEST" if s.is_latest else f"SUPERSEDED (see {s.superseded_by})"
        loc = f", page {s.page}" if s.page else ""
        sec = f", section '{s.section}'" if s.section else ""
        blocks.append(
            f"[{s.n}] {s.title} | {s.doc_id} Rev {s.revision} ({status}) | "
            f"{DOC_TYPE_LABEL.get(s.doc_type, s.doc_type)}{sec}{loc}\n{s.text}"
        )
    return "\n\n".join(blocks)


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[(])|\n+")
_CITE = re.compile(r"\[(\d+)\]")


def split_sentences(answer: str) -> list[str]:
    return [s.strip(" -*") for s in _SENT.split(answer) if len(s.strip(" -*").split()) >= 3]


def verify(answer: str, sources: list[Source]) -> dict:
    """Sentence-level faithfulness with the NLI model + citation precision."""
    by_n = {s.n: s for s in sources}
    rows, pairs_ok, pairs = [], 0, 0
    for sent in split_sentences(answer):
        cited = [int(n) for n in _CITE.findall(sent) if int(n) in by_n]
        hyp = _CITE.sub("", sent).strip()
        if len(hyp.split()) < 3 or hyp.endswith(":"):  # list intros are not claims
            continue
        premises = [by_n[n].text for n in cited] or [s.text for s in sources]
        ent, contra = models.entailment(premises, hyp)
        per_cite = {}
        for n in cited:
            e, _ = models.entailment([by_n[n].text], hyp) if len(cited) > 1 else (ent, contra)
            per_cite[n] = round(e, 3)
            pairs += 1
            pairs_ok += e >= NLI_SUPPORT
        rows.append(
            {
                "text": sent,
                "cited": cited,
                "entailment": round(ent, 3),
                "contradiction": round(contra, 3),
                "supported": ent >= NLI_SUPPORT,
                "citation_entailment": per_cite,
            }
        )
    checked = len(rows)
    faith = sum(r["supported"] for r in rows) / checked if checked else None
    return {
        "sentences": rows,
        "faithfulness": faith,
        "citation_precision": pairs_ok / pairs if pairs else None,
        "uncited_sentences": sum(1 for r in rows if not r["cited"]),
    }


def confidence(gate: float, faith: float | None) -> tuple[float, str]:
    conf = gate if faith is None else 0.45 * gate + 0.55 * faith
    return round(conf, 3), "high" if conf >= 0.75 else "medium" if conf >= 0.5 else "low"


def related_docs(r: Retrieval, n: int = 3) -> list[dict]:
    out, seen = [], set()
    for h in r.hits:
        if h.meta["doc_id"] in seen:
            continue
        seen.add(h.meta["doc_id"])
        out.append(
            {
                "doc_id": h.meta["doc_id"],
                "rev_key": h.meta["rev_key"],
                "title": h.meta["title"],
                "doc_type": h.meta["doc_type"],
                "score": round(h.rerank if h.rerank is not None else h.fused, 3),
            }
        )
        if len(out) >= n:
            break
    return out


def _sql_source(info: dict) -> Source:
    return Source(
        n=1,
        chunk_id="sql",
        doc_id="SQL",
        rev_key="",
        title="Structured query over document metadata and FMEA tables",
        doc_type="sql",
        revision="-",
        is_latest=True,
        superseded_by=None,
        format="sql",
        page=None,
        section="",
        bboxes=[],
        snippet=info["result_text"],
        text=f"SQL: {info['query']}\nResult:\n{info['result_text']}",
        scores={},
    )


def _stream_answer(messages, provider, model, call, steps, cfg) -> Iterator[dict]:
    """Stream tokens, hiding the FOLLOW-UP QUESTIONS section. Returns (answer_text, followups) via StopIteration."""
    followups: list[str] = []
    with steps.step("generate", provider=provider, model=model, prompt_version=cfg.prompt_version) as rec:
        buf, emitted, hidden = "", 0, False
        for delta in llm.stream(messages, provider, model, call):
            buf += delta
            if hidden:
                continue
            pos = buf.lower().find(FOLLOWUP)
            if pos >= 0:
                hidden = True
                if pos > emitted:
                    yield {"event": "token", "data": {"text": buf[emitted:pos].rstrip()}}
                emitted = pos
                continue
            safe = len(buf) - len(FOLLOWUP)
            if safe > emitted:
                yield {"event": "token", "data": {"text": buf[emitted:safe]}}
                emitted = safe
        if not hidden and len(buf) > emitted:
            yield {"event": "token", "data": {"text": buf[emitted:]}}
        pos = buf.lower().find(FOLLOWUP)
        text = (buf[:pos] if pos >= 0 else buf).strip()
        if pos >= 0:
            followups = [ln.strip(" -*0123456789.").strip() for ln in buf[pos + len(FOLLOWUP) :].splitlines()]
            followups = [f for f in followups if len(f) > 8][:3]
        rec.update(
            cached=call.cached,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            first_token_ms=round(call.first_token_ms or 0, 1),
        )
    return text, followups


def answer(
    question: str,
    history: list[dict] | None = None,
    cfg: RuntimeConfig | None = None,
    role: str = DEFAULT_ROLE,
    session_id: str | None = None,
    save: bool = True,
) -> Iterator[dict]:
    """Streamed events: meta, sources, token*, verification, done (or error)."""
    cfg = cfg or load_runtime()
    t0 = time.perf_counter()
    trace_id = uuid.uuid4().hex[:12]
    provider, model = llm.resolve(cfg.llm_provider, cfg.llm_model)
    r = retrieve(question, history, cfg, role, (provider, model))
    steps = r.steps
    yield {
        "event": "meta",
        "data": {
            "trace_id": trace_id,
            "standalone": r.standalone,
            "expanded": r.expanded,
            "filters": r.filters,
            "filters_relaxed": r.filters_relaxed,
            "intent": r.intent,
            "provider": provider,
            "model": model,
            "gate": round(r.gate, 3),
        },
    }
    sources: list[Source] = []
    call = llm.LlmCall(provider, model)
    text, followups, verification = (
        "",
        [],
        {"sentences": [], "faithfulness": None, "citation_precision": None},
    )
    gate = r.gate
    sql_info = None
    if r.intent == "analytical" and cfg.sql_route:
        with steps.step("sql", provider=provider, model=model) as rec:
            sql_info = sqlroute.answer_rows(r.standalone, role, provider, model)
            rec.update(**{k: v for k, v in sql_info.items() if k != "rows"})
        if sql_info.get("rows"):
            yield {"event": "sql", "data": sql_info}
    verified = verified_mod.match(r.standalone, cfg) if cfg.use_verified and r.intent != "chitchat" else None
    if verified:
        yield {
            "event": "verified",
            "data": {k: verified[k] for k in ("id", "question", "status", "similarity")},
        }
    if r.intent == "chitchat":
        text = (
            "Hello! I answer questions from Norvane's engineering record: 8D reports, lessons learned, FMEAs, test "
            "reports, design reviews, ECNs and supplier quality data. Try one of the example questions."
        )
        yield {"event": "token", "data": {"text": text}}
    elif sql_info and sql_info.get("rows"):
        sources = [_sql_source(sql_info)]
        yield {"event": "sources", "data": [_source_public(s) for s in sources]}
        messages = load_prompt("answer", cfg.prompt_version).format_messages(
            context=format_context(sources), question=r.standalone
        )
        text, followups = yield from _stream_answer(messages, provider, model, call, steps, cfg)
        with steps.step("verify", method="sql-consistency") as rec:
            verification = sqlroute.check_answer(text, sql_info)
            rec.update(faithfulness=verification["faithfulness"])
        gate = 1.0
    elif not r.passed_gate and not verified:
        text = ABSTAIN
        yield {"event": "token", "data": {"text": text}}
    else:
        with steps.step("context") as rec:
            sources = build_context(r, cfg, verified)
            rec.update(
                passages=len(sources),
                chars=sum(len(s.text) for s in sources),
                latest_added=sum(1 for s in sources if s.scores.get("added_for")),
                verified_added=bool(verified),
            )
        yield {"event": "sources", "data": [_source_public(s) for s in sources]}
        prompt = load_prompt("answer", cfg.prompt_version)
        messages = prompt.format_messages(context=format_context(sources), question=r.standalone)
        text, followups = yield from _stream_answer(messages, provider, model, call, steps, cfg)
        if verified:
            gate = max(gate, verified["similarity"])
        abstained_by_llm = ABSTAIN.lower().rstrip(".") in text.lower()
        if not abstained_by_llm:
            with steps.step("verify") as rec:
                verification = verify(text, sources)
                rec.update(
                    faithfulness=verification["faithfulness"],
                    citation_precision=verification["citation_precision"],
                )
    abstained = text == ABSTAIN or ABSTAIN.lower().rstrip(".") in text.lower()
    conf, label = confidence(gate, verification["faithfulness"]) if not abstained else (round(gate, 3), "n/a")
    cited = sorted({int(n) for n in _CITE.findall(text)})
    citations = [_source_public(s) for s in sources if s.n in cited]
    invalid = [n for n in cited if n > len(sources)]
    yield {"event": "verification", "data": {**verification, "confidence": conf, "confidence_label": label}}
    latency = round((time.perf_counter() - t0) * 1000, 1)
    done = {
        "trace_id": trace_id,
        "answer": text,
        "abstained": abstained,
        "citations": citations,
        "invalid_citations": invalid,
        "suggestions": followups,
        "related": related_docs(r) if abstained else [],
        "confidence": conf,
        "confidence_label": label,
        "latency_ms": latency,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "stages": {st["name"]: st["ms"] for st in steps},
        "sql": sql_info if sql_info and sql_info.get("rows") else None,
        "verified": {k: verified[k] for k in ("id", "question", "status", "similarity")}
        if verified
        else None,
    }
    if save:
        with session() as s:
            s.add(
                Trace(
                    id=trace_id,
                    session_id=session_id,
                    question=question,
                    standalone=r.standalone,
                    answer=text,
                    abstained=abstained,
                    confidence=conf,
                    confidence_label=label,
                    intent=r.intent,
                    role=role,
                    provider=provider,
                    model=model,
                    prompt_version=cfg.prompt_version,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    latency_ms=latency,
                    data={
                        "steps": steps,
                        "expanded": r.expanded,
                        "expansions": r.expansions,
                        "filters": r.filters,
                        "filters_relaxed": r.filters_relaxed,
                        "intent_detail": r.intent_detail,
                        "retrieved": [_hit_row(h, r.index) for h in r.hits],
                        "sql": sql_info,
                        "verified": done["verified"],
                        "sources": [_source_public(s) for s in sources],
                        "citations": cited,
                        "invalid_citations": invalid,
                        "verification": verification,
                        "suggestions": followups,
                        "config": cfg.model_dump(),
                        "llm_cached": call.cached,
                        "gate": r.gate,
                    },
                )
            )
            s.commit()
    yield {"event": "done", "data": done}


def _source_public(s: Source) -> dict:
    d = asdict(s)
    d["text"] = s.text[:1500]
    d["scores"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.scores.items()}
    return d


def ask(
    question: str,
    history: list[dict] | None = None,
    cfg: RuntimeConfig | None = None,
    role: str = DEFAULT_ROLE,
    save: bool = True,
) -> dict:
    """Non-streaming convenience wrapper (CLI, eval)."""
    out: dict = {"sources": [], "verification": {}}
    for ev in answer(question, history, cfg, role, save=save):
        if ev["event"] in ("meta", "verification", "done"):
            out.update(ev["data"]) if ev["event"] != "verification" else out.update(verification=ev["data"])
        elif ev["event"] == "sources":
            out["sources"] = ev["data"]
    return out
