"""Query understanding: condense follow-ups, expand acronyms/synonyms, extract metadata filters."""

import re

from langchain_core.prompts import ChatPromptTemplate

from yokoten.config import ROOT
from yokoten.ingest import entities
from yokoten.rag import llm

PROMPTS_DIR = ROOT / "backend" / "prompts"


def load_prompt(name: str, version: str) -> ChatPromptTemplate:
    """Versioned prompt file with '## system' and '## human' sections -> LangChain ChatPromptTemplate."""
    text = (PROMPTS_DIR / f"{name}_{version}.md").read_text("utf-8")
    parts = dict(re.findall(r"^## (system|human)\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M))
    return ChatPromptTemplate.from_messages(
        [("system", parts["system"].strip()), ("human", parts["human"].strip())]
    )


def format_history(history: list[dict], max_turns: int = 6) -> str:
    return "\n".join(f"{h['role']}: {h['content']}" for h in history[-max_turns:])


def condense(question: str, history: list[dict], provider: str | None, model: str | None) -> tuple[str, str]:
    """Standalone question for retrieval. LLM rewrite when a provider is given, else a history heuristic."""
    if not history:
        return question, "none"
    if provider and model:
        out = llm.chain(load_prompt("condense", "v1"), provider, model, max_tokens=120).invoke(
            {"history": format_history(history), "question": question}
        )
        out = out.strip().strip('"')
        if out:
            return out.splitlines()[0], f"llm:{provider}"
    last_user = next((h["content"] for h in reversed(history) if h["role"] == "user"), "")
    return f"{last_user} {question}".strip(), "heuristic"


def expand(question: str) -> tuple[str, list[str]]:
    """Append glossary expansions of acronyms and synonyms so BM25 and dense retrieval both see them."""
    g = entities.glossary()
    added = []
    for acro, full in g["acronyms"].items():
        if (
            re.search(rf"(?<![A-Za-z0-9]){re.escape(acro)}(?![A-Za-z0-9])", question)
            and full.lower() not in question.lower()
        ):
            added.append(full)
    low = question.lower()
    for word, syns in g["synonyms"].items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            added += [s for s in syns if s.lower() not in low]
    return (f"{question} ({'; '.join(added)})" if added else question), added


_LIST_Q = re.compile(
    r"^\s*(which|list|show|what)\b.*\b(reports?|lessons?|8ds?|documents?|ecns?|drawings?|"
    r"minutes|instructions?)\b",
    re.I,
)


def extract_filters(question: str) -> dict:
    """Explicit constraints in the question -> metadata filters (component, product line, plant, years, doc type)."""
    q = question
    f: dict = {}
    if m := re.search(r"\bbetween (20\d\d) and (20\d\d)\b", q, re.I):
        f["year_min"], f["year_max"] = int(m.group(1)), int(m.group(2))
    elif m := re.search(r"\bafter (20\d\d)\b", q, re.I):
        f["year_min"] = int(m.group(1)) + 1
    elif m := re.search(
        r"\b(?:since|from) (20\d\d)\b|\b(20\d\d) (?:or later|onwards|and later|and after)\b", q, re.I
    ):
        f["year_min"] = int(m.group(1) or m.group(2))
    elif m := re.search(r"\b(?:before|prior to) (20\d\d)\b", q, re.I):
        f["year_max"] = int(m.group(1)) - 1
    elif m := re.search(r"\b(?:in|during) (20\d\d)\b", q, re.I):
        f["year_min"] = f["year_max"] = int(m.group(1))
    if comps := entities.components_in(q):
        f["component"] = comps
    if lines := entities.product_lines_in(q):
        f["product_line"] = lines
    if plants := entities.plants_in(q):
        f["plant"] = plants
    if _LIST_Q.search(q) and (types := entities.doc_types_in(q)):
        f["doc_type"] = types
    return f
