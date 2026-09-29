from pathlib import Path

import cv2
import numpy as np
from langchain_core.documents import Document as LCDocument

from yokoten.ingest import entities
from yokoten.ingest.chunking import chunk
from yokoten.ingest.loaders import parse_md
from yokoten.ingest.ocr import estimate_skew, extract_fields, fix_ocr_text, rotate
from yokoten.retrieval.index import Index, tokenize


def _el(text, kind="text", section="S", page=1, bbox=(0, 0, 10, 10)):
    return LCDocument(
        page_content=text, metadata={"kind": kind, "section": section, "page": page, "bbox": list(bbox)}
    )


def test_parent_child_links_children_to_parents():
    els = [
        _el("Root cause", "heading", "D4"),
        _el("word " * 200, section="D4"),
        _el("a | b\n1 | 2", "table", "D4"),
    ]
    out = chunk(els, "parent_child")
    parents = [c for c in out if c.kind == "parent"]
    children = [c for c in out if c.kind != "parent"]
    assert parents and children and all(not p.indexed for p in parents)
    assert all(out[c.parent_idx].kind == "parent" for c in children)
    assert any(c.kind == "table" for c in children)


def test_offset_chunks_keep_page_locations():
    els = [_el(f"paragraph {i} " * 40, page=i) for i in range(1, 4)]
    for strategy in ("fixed", "recursive"):
        out = chunk(els, strategy)
        assert out and all(c.page for c in out) and all(c.bboxes for c in out)


def test_markdown_tables_and_sections(tmp_path: Path):
    p = tmp_path / "x.md"
    p.write_text("# Title\n\n## Why\nBecause.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", "utf-8")
    els = parse_md(p).elements
    assert [e.kind for e in els] == ["heading", "heading", "text", "table"]
    assert els[3].text == "A | B\n1 | 2" and els[3].section == "Why"


def test_ocr_text_repair_and_title_block_fields():
    assert fix_ocr_text("MATERIAL PA6-GF3O V0") == "MATERIAL PA6-GF30 V0"
    assert fix_ocr_text("PART NO BMS - 91020") == "PART NO BMS-91020"
    f = extract_fields(
        "TITLE ECU HOUSING COVER\nPART NO BMS-91020\nMATERIAL PA6-GF30 V0\nREV B\nDECISION: REJECT"
    )
    assert f["part_number"] == "BMS-91020" and f["revision"] == "B" and f["material"] == "PA6-GF30 V0"
    assert f["decision"] == "REJECT"


def test_deskew_recovers_rotation():
    img = np.full((600, 900), 255, np.uint8)
    for y in range(80, 560, 40):
        cv2.putText(img, "LOREM IPSUM TEXT LINE 12345", (40, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    skewed = rotate(img, 3.0)
    _, inv = cv2.threshold(skewed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    assert abs(estimate_skew(inv) + 3.0) <= 0.5


def test_regex_entities_and_glossary():
    e = entities.regex_entities(
        "8D-INV-22-007 for INV-70455 on P-INV-2104 (ECN-2022-003), lot A-23-2210 in 2022"
    )
    assert e["part_numbers"] == ["INV-70455"] and e["projects"] == ["P-INV-2104"]
    assert "8D-INV-22-007" in e["doc_refs"] and "ECN-2022-003" in e["doc_refs"] and e["lots"] == ["A-23-2210"]
    assert entities.components_in("solder fatigue in the traction inverter") == ["INV"]
    assert entities.plants_in("at the Toluca plant") == ["TLC"]


def test_tokenize_keeps_codes_and_parts():
    toks = tokenize("The INV-70455 module failed at 1,500 rpm")
    assert "inv-70455" in toks and "70455" in toks and "the" not in toks


def test_chroma_where():
    assert Index.chroma_where(None) is None
    assert Index.chroma_where({"doc_type": ["8d"]}) == {"doc_type": {"$in": ["8d"]}}
    w = Index.chroma_where({"component": ["INV"], "year_min": 2023})
    assert w == {
        "$and": [
            {"$or": [{"component": {"$in": ["INV"]}}, {"component": ""}]},
            {"$or": [{"year": {"$gte": 2023}}, {"year": 0}]},
        ]
    }
