"""Integration + end-to-end smoke tests: a small real ingest, the search API, the SSE chat flow."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from yokoten.config import ROOT, settings

SUBSET_TYPES = {"8d", "lessons_learned", "supplier_quality", "test_report"}


@pytest.fixture(scope="module")
def client():
    from yokoten.ingest.pipeline import ingest_file, update_latest_flags
    from yokoten.retrieval.index import bump_index_version

    if not (settings.corpus_dir / "manifest.json").exists():
        from yokoten.datagen import generate

        generate(settings.corpus_dir, ROOT / "eval" / "golden.jsonl")
    from yokoten.db import init_db

    init_db()
    manifest = json.loads((settings.corpus_dir / "manifest.json").read_text("utf-8"))["documents"]
    subset = [
        m
        for m in manifest
        if m["doc_type"] in SUBSET_TYPES and m["component"] in ("INV", None) and m["year"] in (2022, 2023)
    ]
    for m in subset:
        ingest_file(settings.corpus_dir / m["file"], m, ner=False)
    update_latest_flags()
    bump_index_version()
    from yokoten.api import app

    return TestClient(app)


def _sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        name = next((ln[7:] for ln in block.splitlines() if ln.startswith("event: ")), "message")
        data = "\n".join(ln[6:] for ln in block.splitlines() if ln.startswith("data: "))
        if data:
            events.append((name, json.loads(data)))
    return events


def test_search_finds_the_right_document(client):
    r = client.post(
        "/api/search", json={"query": "root cause of power module die-attach solder fatigue", "k": 5}
    )
    assert r.status_code == 200
    top = r.json()["results"][0]
    assert top["doc_id"].startswith(("8D-INV-22", "LL-INV-22", "TR-INV-22"))
    assert {"dense", "bm25", "fused", "rerank"} <= set(top["scores"])


def test_chat_abstains_on_unanswerable_question_without_llm(client):
    r = client.post(
        "/api/chat", json={"question": "What was the warranty cost in US dollars of the headlamp recall?"}
    )
    assert r.status_code == 200
    events = _sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "session" and "meta" in names and names[-1] == "done"
    done = events[-1][1]
    assert done["abstained"] is True and done["related"]
    trace = client.get(f"/api/traces/{done['trace_id']}").json()
    assert [s["name"] for s in trace["data"]["steps"]][:6] == [
        "condense",
        "expand",
        "filters",
        "intent",
        "retrieve",
        "rerank",
    ]


def test_document_page_render_with_highlight(client):
    docs = client.get("/api/documents", params={"doc_type": "8d"}).json()
    d = next(x for x in docs if x["format"] == "pdf")
    detail = client.get(f"/api/documents/{d['rev_key']}").json()
    chunk = next(c for c in detail["chunks"] if c["page"] and c["kind"] != "parent")
    r = client.get(f"/api/documents/{d['rev_key']}/page/{chunk['page']}", params={"chunk": chunk["id"]})
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


def test_upload_rejects_unsupported_type(client):
    r = client.post("/api/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


@pytest.mark.skipif(
    not (os.environ.get("YOKOTEN_TEST_LLM") or settings.groq_api_key),
    reason="needs an LLM (set GROQ_API_KEY or YOKOTEN_TEST_LLM=local)",
)
def test_chat_answers_with_citations(client):
    cfg = {"llm_provider": os.environ.get("YOKOTEN_TEST_LLM", "groq")}
    r = client.post(
        "/api/chat",
        json={
            "question": "What was the root cause of the inverter power module solder "
            "fatigue on project P-INV-2104?",
            "config": cfg,
        },
    )
    events = _sse(r.text)
    done = events[-1][1]
    assert not done["abstained"] and "void" in done["answer"].lower()
    assert any(e == "token" for e, _ in events) and any(e == "sources" for e, _ in events)
