"""Onboarding digest: a cited brief for a new engineer on one component or product line."""

import re
from collections import Counter

from yokoten.db import Chunk, Document, FmeaItem, select, session
from yokoten.domain import DOC_TYPE_LABEL, ROLE_ACCESS
from yokoten.ingest.entities import glossary
from yokoten.rag import llm
from yokoten.rag.query import load_prompt

AP_ORDER = {"H": 0, "M": 1, "L": 2}


def _docs(component: str | None, product_line: str | None, role: str) -> list[Document]:
    with session() as s:
        stmt = select(Document).where(
            Document.status == "ready", Document.is_latest, Document.classification.in_(ROLE_ACCESS[role])
        )
        stmt = (
            stmt.where(Document.component == component)
            if component
            else stmt.where(Document.product_line == product_line)
        )
        return list(s.exec(stmt).all())


def _ref(d: Document) -> dict:
    return {
        "doc_id": d.doc_id,
        "rev_key": d.rev_key,
        "title": d.title,
        "doc_type": d.doc_type,
        "doc_type_label": DOC_TYPE_LABEL.get(d.doc_type, d.doc_type),
        "year": d.year,
    }


def _lesson_text(rev_key: str) -> str:
    with session() as s:
        chunks = s.exec(select(Chunk).where(Chunk.rev_key == rev_key, Chunk.strategy == "structure")).all()
    for c in chunks:
        if c.section.strip().lower() == "lesson learned":
            return re.sub(r"^Lesson learned\s*", "", c.text).strip()
    return ""


def digest(component: str | None = None, product_line: str | None = None, role: str = "admin") -> dict:
    docs = _docs(component, product_line, role)
    comps = {component} if component else {d.component for d in docs if d.component}
    by_type: dict[str, list[Document]] = {}
    for d in sorted(docs, key=lambda d: (-(d.year or 0), d.doc_id)):
        by_type.setdefault(d.doc_type, []).append(d)
    issues = [
        {**_ref(d), "project": d.project, "plant": d.plant, "suppliers": d.suppliers}
        for d in by_type.get("8d", [])
    ]
    lessons = [{**_ref(d), "lesson": _lesson_text(d.rev_key)} for d in by_type.get("lessons_learned", [])]
    with session() as s:
        fmea = s.exec(
            select(FmeaItem).where(
                FmeaItem.is_latest, FmeaItem.fmea_type == "dfmea", FmeaItem.component.in_(comps)
            )
        ).all()
    fmea_rows = sorted(fmea, key=lambda r: (AP_ORDER.get(r.action_priority, 3), -r.severity))[:10]
    with session() as s:
        latest = {
            d.doc_id: d.rev_key
            for d in s.exec(
                select(Document).where(Document.is_latest, Document.doc_id.in_({r.doc_id for r in fmea_rows}))
            ).all()
        }
    must_read = [
        _ref(d)
        for t in ("dfmea", "lessons_learned", "dvpr", "work_instruction", "design_review")
        for d in by_type.get(t, [])[: 3 if t == "lessons_learned" else 1]
    ]
    text = " ".join(
        [i["title"] for i in issues]
        + [x["lesson"] for x in lessons]
        + [f"{r.failure_mode} {r.cause} {r.recommended_action}" for r in fmea_rows]
    )
    for d in docs:
        text += " " + d.title
    acr = glossary()["acronyms"]
    found = Counter(a for a in acr if re.search(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", text))
    for d in docs:
        with session() as s:
            body = " ".join(
                c.text
                for c in s.exec(
                    select(Chunk).where(Chunk.rev_key == d.rev_key, Chunk.strategy == "structure")
                ).all()
            )
        found.update(a for a in acr if re.search(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", body))
    return {
        "component": component,
        "product_line": product_line,
        "documents": len(docs),
        "issues": issues,
        "lessons": lessons,
        "failure_modes": [
            {
                "failure_mode": r.failure_mode,
                "item": r.item,
                "effect": r.effect,
                "cause": r.cause,
                "severity": r.severity,
                "occurrence": r.occurrence,
                "detection": r.detection,
                "action_priority": r.action_priority,
                "status": r.status,
                "doc_id": r.doc_id,
                "rev_key": latest.get(r.doc_id, f"{r.doc_id}@{r.revision}"),
                "revised_action_priority": r.revised_action_priority,
            }
            for r in fmea_rows
        ],
        "must_read": must_read,
        "glossary": [{"term": a, "meaning": acr[a], "mentions": n} for a, n in found.most_common(18)],
    }


def summary(d: dict, provider: str | None = None, model: str | None = None) -> dict:
    """LLM-written, cited brief over the lessons + top FMEA items gathered by digest()."""
    passages = [
        {
            "n": i + 1,
            "doc_id": x["doc_id"],
            "rev_key": x["rev_key"],
            "title": x["title"],
            "text": f"Lesson ({x['title']}): {x['lesson']}",
        }
        for i, x in enumerate(d["lessons"])
        if x["lesson"]
    ]
    for r in d["failure_modes"][:6]:
        passages.append(
            {
                "n": len(passages) + 1,
                "doc_id": r["doc_id"],
                "rev_key": r["rev_key"],
                "title": f"DFMEA item: {r['failure_mode']}",
                "text": f"DFMEA: failure mode '{r['failure_mode']}' ({r['item']}), effect {r['effect']}, "
                f"cause {r['cause']}, S={r['severity']} O={r['occurrence']} D={r['detection']} "
                f"AP={r['action_priority']}.",
            }
        )
    if not passages:
        return {"text": "", "sources": [], "provider": None, "model": None}
    provider, model = llm.resolve(provider, model)
    product = d["component"] or d["product_line"]
    text = llm.chain(load_prompt("digest", "v1"), provider, model, max_tokens=600).invoke(
        {"product": product, "context": "\n\n".join(f"[{p['n']}] {p['text']}" for p in passages)}
    )
    return {
        "text": text.strip(),
        "sources": passages,
        "provider": provider,
        "model": model,
        "chain": "LCEL prompt | model | parser",
    }
