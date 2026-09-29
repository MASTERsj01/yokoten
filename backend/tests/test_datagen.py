from collections import Counter

import pytest

from yokoten.datagen.docs import Corpus, action_priority, num_facts


@pytest.fixture(scope="module")
def corpus():
    return Corpus(seed=42).build()


def _text(doc) -> str:
    parts = [doc.title]
    for b in doc.blocks:
        if b[0] in ("p", "h"):
            parts.append(str(b[-1]))
        elif b[0] == "list":
            parts += b[1]
        elif b[0] == "kv":
            parts += [f"{k} {v}" for k, v in b[1]]
        elif b[0] == "table":
            parts += [" ".join(map(str, r)) for r in b[2]]
    for _, header, rows in doc.sheets:
        parts += [" ".join(map(str, r)) for r in [header, *rows]]
    return " ".join(parts).lower()


def test_action_priority_examples():
    assert action_priority(9, 5, 6) == "H"
    assert action_priority(9, 2, 3) == "L"
    assert action_priority(7, 2, 4) == "L"
    assert action_priority(5, 2, 4) == "L"


def test_num_facts():
    assert num_facts("1,500 rpm") == ["1500"]
    assert num_facts("peroxide-cured EPDM") == ["peroxide-cured epdm"]


def test_corpus_size_and_types(corpus):
    assert 150 <= len(corpus.docs) <= 250
    types = Counter(d.doc_type for d in corpus.docs)
    assert {
        "8d",
        "lessons_learned",
        "dfmea",
        "pfmea",
        "test_report",
        "design_review",
        "ecn",
        "supplier_quality",
        "work_instruction",
        "field_failure",
        "drawing",
        "inspection_record",
        "dvpr",
    } <= set(types)
    assert {d.fmt for d in corpus.docs} == {"pdf", "docx", "xlsx", "md", "png", "jpg"}
    # superseded revisions exist and point at each other
    assert any(d.superseded_by for d in corpus.docs) and any(d.supersedes for d in corpus.docs)


def test_golden_set_is_consistent(corpus):
    qs = corpus.qs
    ids = {d.id for d in corpus.docs}
    assert 110 <= len(qs) <= 140
    cats = Counter(q["category"] for q in qs)
    assert 0.12 <= cats["unanswerable"] / len(qs) <= 0.18
    for q in qs:
        for group in q["gold"]:
            assert any(g in ids for g in group), (q["question"], group)
        if q["category"] not in ("unanswerable",):
            assert q["answer_facts"], q["question"]
    for cat in cats:
        splits = {q["split"] for q in qs if q["category"] == cat}
        assert splits == {"dev", "test"}, cat


def test_ocr_answers_only_exist_in_scans(corpus):
    text_docs = " ".join(_text(d) for d in corpus.docs if d.fmt not in ("png", "jpg"))
    ocr = [q for q in corpus.qs if q["category"] == "ocr"]
    assert len(ocr) >= 10
    for q in ocr:
        # the part number / lot the question is about never appears in a text document
        key = (
            q["gold"][0][0].removeprefix("DWG-")
            if q["gold"][0][0].startswith("DWG-")
            else q["question"].split("lot ")[1].split()[0]
        )
        assert key.lower() not in text_docs, q["question"]
