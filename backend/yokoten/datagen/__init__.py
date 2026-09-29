"""Seeded, reproducible synthetic corpus + golden set. Entry point: generate()."""

import json
import random
import shutil
from collections import Counter
from pathlib import Path

from yokoten.datagen.docs import Corpus
from yokoten.datagen.render import render

SCAN_META_KEYS = ("doc_id", "title", "doc_type", "format", "file", "year", "date", "classification")


def generate(out_dir: Path, golden_path: Path, seed: int = 42) -> dict:
    corpus = Corpus(seed).build()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    rng = random.Random(seed)
    manifest = []
    for doc in corpus.docs:
        render(doc, out_dir, rng)
        meta = doc.meta()
        if doc.fmt in (
            "png",
            "jpg",
        ):  # scans: a DMS only knows what was typed at upload; the rest comes from OCR
            meta = {k: meta[k] for k in SCAN_META_KEYS} | {"scanned": True}
        manifest.append(meta)
    (out_dir / "manifest.json").write_text(
        json.dumps({"seed": seed, "documents": manifest}, indent=1), "utf-8"
    )
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    with golden_path.open("w", encoding="utf-8") as f:
        for q in corpus.qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    return {
        "documents": len(manifest),
        "by_type": dict(Counter(d["doc_type"] for d in manifest)),
        "by_format": dict(Counter(d["format"] for d in manifest)),
        "questions": len(corpus.qs),
        "by_category": dict(Counter(q["category"] for q in corpus.qs)),
        "by_split": dict(Counter(q["split"] for q in corpus.qs)),
    }
