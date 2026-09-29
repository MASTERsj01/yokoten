"""Entity extraction: regex for engineering codes + glossary lookups + a Hugging Face NER model for organisations."""

import json
import re
from functools import cache

from yokoten.config import device, settings

NER_MODEL = "dslim/distilbert-NER"

PATTERNS = {
    "part_numbers": re.compile(r"\b(?:RAD|HVC|CMP|INJ|SNS|INV|DCD|BMS|WPM|EPS)-\d{5}\b"),
    "projects": re.compile(r"\bP-[A-Z]{3}-\d{4}\b"),
    "doc_refs": re.compile(
        r"\b(?:8D|LL|TR|FFA)-[A-Z]{3}-\d{2}-\d{3}\b|\bECN-\d{4}-\d{3}\b|\b(?:DFMEA|PFMEA|SQR|DWG|DVP)-[A-Z0-9-]+\b"
    ),
    "years": re.compile(r"\b(?:19|20)\d{2}\b"),
    "lots": re.compile(r"\b[A-Z]-\d{2}-\d{4}\b"),
}


@cache
def glossary() -> dict:
    return json.loads((settings.data_dir / "glossary.json").read_text("utf-8"))


def regex_entities(text: str) -> dict[str, list[str]]:
    out = {k: sorted(set(rx.findall(text))) for k, rx in PATTERNS.items()}
    return {k: v for k, v in out.items() if v}


def _find_keys(text: str, table: dict) -> list[str]:
    low = f" {text.lower()} "
    hits = []
    for key, val in table.items():
        words = val["keywords"] if isinstance(val, dict) else val
        if any(re.search(rf"(?<![a-z0-9]){re.escape(w.strip())}(?![a-z0-9])", low) for w in words):
            hits.append(key)
    return hits


def components_in(text: str) -> list[str]:
    return _find_keys(text, glossary()["components"])


def plants_in(text: str) -> list[str]:
    return _find_keys(text, glossary()["plants"])


def product_lines_in(text: str) -> list[str]:
    return _find_keys(text, glossary()["product_lines"])


def doc_types_in(text: str) -> list[str]:
    return _find_keys(text, glossary()["doc_types"])


@cache
def _ner():
    from transformers import pipeline

    return pipeline(
        "token-classification",
        model=NER_MODEL,
        aggregation_strategy="simple",
        device=0 if device() == "cuda" else -1,
    )


def organisations(text: str, max_chars: int = 6000) -> list[str]:
    """Organisation names (suppliers, customers) found by the NER model, windowed over the document."""
    ner = _ner()
    windows = [text[i : i + 1500] for i in range(0, min(len(text), max_chars), 1500)]
    orgs: dict[str, float] = {}
    for window_ents in ner(windows):
        for ent in window_ents:
            name = ent["word"].strip(" .,;:")
            if ent["entity_group"] == "ORG" and ent["score"] >= 0.8 and len(name) > 2 and "#" not in name:
                orgs[name] = max(orgs.get(name, 0), float(ent["score"]))
    return sorted(orgs, key=orgs.get, reverse=True)


def infer_metadata(text: str, filename: str = "") -> dict:
    """Best-effort metadata for uploaded files (corpus files come with a manifest)."""
    ents = regex_entities(text)
    comps = components_in(text[:3000]) or [p.split("-")[0] for p in ents.get("part_numbers", [])]
    comp = max(set(comps), key=comps.count) if comps else None
    types = doc_types_in(f"{filename} {text[:600]}")
    years = [int(y) for y in ents.get("years", []) if 2000 <= int(y) <= 2035]
    plants = plants_in(text[:3000])
    return {
        "doc_type": types[0] if types else "other",
        "component": comp,
        "product_line": glossary()["components"][comp]["line"] if comp else None,
        "project": ents.get("projects", [None])[0],
        "plant": plants[0] if plants else None,
        "year": max(years) if years else None,
        "part_numbers": ents.get("part_numbers", []),
    }
