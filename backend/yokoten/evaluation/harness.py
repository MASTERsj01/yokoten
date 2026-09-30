"""Evaluation harness: retrieval ablations (no LLM), abstention calibration, generation metrics, OCR, system.

One command: `yokoten eval` -> eval/results/<run_id>.json (+ latest.json, SQLite EvalRun) + docs/EVALUATION_REPORT.md
"""

import json
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from yokoten.config import ROOT, RuntimeConfig, device, load_runtime, settings
from yokoten.evaluation.metrics import (
    abstention_scores,
    aggregate,
    calibrate_threshold,
    doc_ranking,
    fact_present,
    fact_score,
    mean,
    pct,
    retrieval_metrics,
)
from yokoten.rag import llm
from yokoten.rag.pipeline import ABSTAIN, ask, retrieve
from yokoten.rag.query import load_prompt
from yokoten.retrieval.embeddings import EMBED_MODELS

GOLDEN = ROOT / "eval" / "golden.jsonl"
RESULTS = ROOT / "eval" / "results"
RET_KEYS = ["recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10"]
STAGES = [
    "condense",
    "expand",
    "filters",
    "intent",
    "retrieve",
    "rerank",
    "gate",
    "context",
    "generate",
    "verify",
]


def load_golden(split: str | None = None) -> list[dict]:
    qs = [json.loads(line) for line in GOLDEN.read_text("utf-8").splitlines() if line.strip()]
    return [q for q in qs if split in (None, "all") or q["split"] == split]


# ------------------------------------------------------------------ retrieval
def run_retrieval(cfg: RuntimeConfig, questions: list[dict]) -> list[dict]:
    rows = []
    for q in questions:
        t = time.perf_counter()
        r = retrieve(q["question"], q.get("history"), cfg, role="admin", llm_for_condense=None)
        ranked = doc_ranking([h.meta["doc_id"] for h in r.hits])
        row = {
            "id": q["id"],
            "category": q["category"],
            "split": q["split"],
            "gate": r.gate,
            "passed": r.passed_gate,
            "ranked": ranked[:10],
            "latency_ms": (time.perf_counter() - t) * 1000,
            "stages": {s["name"]: s["ms"] for s in r.steps},
            "filters": r.filters,
        }
        if q["gold"]:
            row.update(retrieval_metrics(ranked, q["gold"]))
        rows.append(row)
    return rows


def summarize_retrieval(rows: list[dict]) -> dict:
    scored = [r for r in rows if "mrr" in r]
    by_cat = defaultdict(list)
    for r in scored:
        by_cat[r["category"]].append(r)
    return {
        "overall": aggregate(scored, RET_KEYS),
        "by_category": {c: aggregate(v, RET_KEYS) for c, v in by_cat.items()},
        "latency_p50_ms": pct([r["latency_ms"] for r in rows], 50),
    }


def _score(summary: dict) -> float:
    o = summary["overall"]
    return (o["recall@5"] or 0) + (o["mrr"] or 0)


ABLATIONS: list[tuple[str, list[tuple[str, dict]]]] = [
    ("chunking", [(v, {"chunking": v}) for v in ("fixed", "recursive", "structure", "parent_child")]),
    ("embedding_model", [(m.split("/")[-1], {"embedding_model": m}) for m in EMBED_MODELS]),
    ("retrieval_mode", [(v, {"retrieval_mode": v}) for v in ("dense", "bm25", "hybrid")]),
    ("reranker", [("off", {"reranker": False}), ("on", {"reranker": True})]),
    ("candidates", [(str(v), {"candidates": v}) for v in (10, 20, 30, 50)]),
    ("query_rewrite", [("off", {"query_rewrite": False}), ("on", {"query_rewrite": True})]),
    ("metadata_filters", [("off", {"use_filters": False}), ("on", {"use_filters": True})]),
    (
        "vector_store",
        [
            ("faiss-flat", {"vector_store": "faiss", "faiss_index": "flat"}),
            ("faiss-hnsw", {"vector_store": "faiss", "faiss_index": "hnsw"}),
            ("chroma", {"vector_store": "chroma"}),
        ],
    ),
]


def _cached_summary(cfg: RuntimeConfig, questions: list[dict]) -> dict:
    """Retrieval summaries are cached per (config, question set, index version) so reruns only redo what changed."""
    import hashlib

    from yokoten.retrieval.index import index_version

    key = hashlib.sha256(
        json.dumps(
            [cfg.model_dump(), [q["id"] for q in questions], index_version(), GOLDEN.stat().st_mtime],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]
    path = settings.var_dir / "eval_cache" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    summary = summarize_retrieval(run_retrieval(cfg, questions))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), "utf-8")
    return summary


def run_ablations(
    base: RuntimeConfig, dev: list[dict], test: list[dict], log=print
) -> tuple[RuntimeConfig, list]:
    """One variable at a time. Greedy tuning on DEV (ties keep the current setting); TEST numbers are reported."""
    chosen = base.model_copy()
    table = []
    for group, variants in ABLATIONS:
        results = []
        for name, update in variants:
            cfg = chosen.model_copy(update=update)
            t = time.perf_counter()
            dev_s, test_s = _cached_summary(cfg, dev), _cached_summary(cfg, test)
            log(
                f"  {group:17s} {name:22s} dev R@5={dev_s['overall']['recall@5']:.3f} MRR={dev_s['overall']['mrr']:.3f} "
                f"| test R@5={test_s['overall']['recall@5']:.3f} ({time.perf_counter() - t:.0f}s)"
            )
            results.append((name, update, dev_s, test_s))
        current = next(
            (r for r in results if all(getattr(chosen, k) == v for k, v in r[1].items())), results[-1]
        )
        best = max(results, key=lambda r: _score(r[2]))
        winner = best if _score(best[2]) > _score(current[2]) + 0.005 else current
        chosen = chosen.model_copy(update=winner[1])
        for name, update, dev_s, test_s in results:
            table.append(
                {
                    "group": group,
                    "variant": name,
                    "chosen": name == winner[0],
                    "metrics": {**test_s["overall"], "latency_p50_ms": test_s["latency_p50_ms"]},
                    "dev": {**dev_s["overall"], "latency_p50_ms": dev_s["latency_p50_ms"]},
                }
            )
    # first-stage quality: embedding models without BM25 or reranking (the full pipeline hides their differences)
    for m in EMBED_MODELS:
        cfg = chosen.model_copy(update={"embedding_model": m, "retrieval_mode": "dense", "reranker": False})
        dev_s, test_s = _cached_summary(cfg, dev), _cached_summary(cfg, test)
        log(f"  {'dense_only_embed':17s} {m.split('/')[-1]:22s} test R@5={test_s['overall']['recall@5']:.3f}")
        table.append(
            {
                "group": "embedding_dense_only",
                "variant": m.split("/")[-1],
                "chosen": m == chosen.embedding_model,
                "metrics": {**test_s["overall"], "latency_p50_ms": test_s["latency_p50_ms"]},
                "dev": {**dev_s["overall"], "latency_p50_ms": dev_s["latency_p50_ms"]},
            }
        )
    return chosen, table


# ------------------------------------------------------------------ generation
def _judge_provider(gen_provider: str) -> tuple[str, str] | None:
    avail = llm.available()
    for p in ["gemini", "groq"] if gen_provider != "gemini" else ["groq"]:
        if avail[p] and p != gen_provider:
            return llm.resolve(p, None)
    return None


def judge(q: dict, answer: str, jp: tuple[str, str]) -> float | None:
    text = llm.chain(load_prompt("judge", "v1"), *jp, max_tokens=120).invoke(
        {"question": q["question"], "reference": q["reference_answer"], "candidate": answer}
    )
    m = re.search(r'"score"\s*:\s*([01](?:\.5)?|0?\.5)', text)
    return float(m.group(1)) if m else None


def run_generation(cfg: RuntimeConfig, questions: list[dict], log=print) -> list[dict]:
    provider, model = llm.resolve(cfg.llm_provider, cfg.llm_model)
    jp = _judge_provider(provider)
    rows = []
    for i, q in enumerate(questions, start=1):
        t = time.perf_counter()
        res = ask(q["question"], q.get("history"), cfg, role="admin", save=False)
        v = res.get("verification", {})
        answer = res.get("answer", "")
        abstained = bool(res.get("abstained"))
        unanswerable = q["category"] == "unanswerable"
        sentences = v.get("sentences") or []
        row = {
            "id": q["id"],
            "category": q["category"],
            "answer": answer,
            "abstained": abstained,
            "unanswerable": unanswerable,
            "correctness": (1.0 if abstained else 0.0)
            if unanswerable
            else fact_score(answer, q["answer_facts"]),
            "missing_facts": [f for f in q["answer_facts"] if not fact_present(answer, f)],
            "faithfulness": v.get("faithfulness"),
            "citation_precision": v.get("citation_precision"),
            "cited": bool(re.search(r"\[\d+\]", answer)),
            "unsupported": sum(not s["supported"] for s in sentences),
            "confidence": res.get("confidence"),
            "gate": res.get("gate"),
            "sources": [s["doc_id"] for s in res.get("sources", [])],
            "latency_ms": (time.perf_counter() - t) * 1000,
            "input_tokens": res.get("input_tokens"),
            "output_tokens": res.get("output_tokens"),
            "stages": res.get("stages", {}),
        }
        if jp:
            row["judge"] = judge(q, ABSTAIN if abstained else answer, jp)
        rows.append(row)
        log(
            f"    [{i}/{len(questions)}] {q['id']} {q['category']:14s} correct={row['correctness']} "
            f"abst={abstained} {row['latency_ms'] / 1000:.1f}s"
        )
    return rows


def summarize_generation(rows: list[dict]) -> dict:
    answered = [r for r in rows if not r["abstained"]]
    ans_q = [r for r in rows if not r["unanswerable"]]
    m = {
        "correctness": mean(r["correctness"] for r in ans_q),
        "judge_correctness": mean(r.get("judge") for r in rows),
        "faithfulness": mean(r["faithfulness"] for r in answered),
        "citation_precision": mean(r["citation_precision"] for r in answered),
        "cited_answers": mean(float(r["cited"]) for r in answered) if answered else None,
        "hallucination_rate": mean(float(r["unsupported"] > 0 or r["unanswerable"]) for r in answered)
        if answered
        else None,
        **abstention_scores([r["abstained"] for r in rows], [r["unanswerable"] for r in rows]),
        "latency_p50_ms": pct([r["latency_ms"] for r in rows], 50),
        "input_tokens": mean(r["input_tokens"] for r in answered),
        "output_tokens": mean(r["output_tokens"] for r in answered),
    }
    m.pop("abstention_f1", None)
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    return {
        "metrics": m,
        "by_category": {
            c: {
                "correctness": mean(x["correctness"] for x in v),
                "judge": mean(x.get("judge") for x in v),
                "n": len(v),
            }
            for c, v in by_cat.items()
        },
    }


def stratified(questions: list[dict], limit: int | None) -> list[dict]:
    if not limit or limit >= len(questions):
        return questions
    by_cat = defaultdict(list)
    for q in questions:
        by_cat[q["category"]].append(q)
    out, i = [], 0
    while len(out) < limit:
        for cat in sorted(by_cat):
            if i < len(by_cat[cat]) and len(out) < limit:
                out.append(by_cat[cat][i])
        i += 1
    return out


# ------------------------------------------------------------------ OCR
def run_ocr(engines: list[str], log=print) -> dict:
    """Field accuracy of each OCR engine (and without preprocessing) on the scans, vs generator ground truth."""
    from yokoten.datagen.docs import DRAWINGS, INSPECTIONS
    from yokoten.ingest.ocr import available_engines, extract_fields, ocr

    manifest = json.loads((settings.corpus_dir / "manifest.json").read_text("utf-8"))["documents"]
    files = {m["doc_id"]: settings.corpus_dir / m["file"] for m in manifest if m.get("scanned")}
    truth = {}
    for _, part, title, material, finish, rev, *_ in DRAWINGS:
        truth[f"DWG-{part}"] = {
            "part_number": part,
            "revision": rev,
            "material": material,
            "title": title.upper(),
        }
    ir_ids = sorted(k for k in files if k.startswith("IR-"))
    by_plant_year = defaultdict(list)
    for plant, sup, part, pname, lot, year, rows, decision in INSPECTIONS:
        by_plant_year[(plant, str(year)[2:])].append((lot, rows, decision, part))
    for iid in ir_ids:
        _, plant, yy, n = iid.split("-")
        lot, rows, decision, part = by_plant_year[(plant, yy)][int(n) - 1]
        truth[iid] = {
            "lot": lot,
            "decision": decision,
            "part_number": part,
            **{f"measured_{i}": r[2] for i, r in enumerate(rows)},
        }
    out = {}
    for engine in [e for e in engines if e in available_engines()]:
        for prep in (True, False):
            name = f"{engine}{'' if prep else ' (no preprocessing)'}"
            hits, total, t0, conf = 0, 0, time.perf_counter(), []
            for doc_id, fields in truth.items():
                res = ocr(files[doc_id], engine=engine, use_preprocessing=prep)
                got = extract_fields(res.text)
                text = re.sub(r"\s+", " ", res.text.upper())
                conf.append(res.confidence)
                for k, v in fields.items():
                    total += 1
                    ok = (
                        (got.get(k, "").upper() == v.upper())
                        if k in ("part_number", "revision", "lot", "decision")
                        else re.sub(r"\s+", " ", v.upper()) in text
                    )
                    hits += ok
            out[name] = {
                "field_accuracy": hits / total,
                "mean_confidence": mean(conf),
                "seconds_per_page": (time.perf_counter() - t0) / len(truth),
            }
            log(f"  OCR {name}: field accuracy {hits}/{total}")
    return out


# ------------------------------------------------------------------ public NHTSA collection
def run_public(cfg: RuntimeConfig) -> dict | None:
    path = ROOT / "eval" / "public_golden.jsonl"
    if not path.exists():
        return None
    qs = [json.loads(x) | {"split": "test"} for x in path.read_text("utf-8").splitlines() if x.strip()]
    rows = run_retrieval(cfg.model_copy(update={"collections": ["public_recalls"]}), qs)
    if not any(r.get("ranked") for r in rows):
        return None  # collection not ingested
    s = summarize_retrieval(rows)
    return {
        "n": len(qs),
        "overall": s["overall"],
        "by_category": s["by_category"],
        "latency_p50_ms": s["latency_p50_ms"],
    }


# ------------------------------------------------------------------ failure analysis
def explain_failures(
    gen_rows: list[dict], ret_rows: dict[str, dict], golden: dict[str, dict], threshold: float, n: int = 8
) -> list[dict]:
    cands = []
    for r in gen_rows:
        q, rr = golden[r["id"]], ret_rows.get(r["id"], {})
        gold_docs = [g for grp in q["gold"] for g in grp]
        ranks = {d: i + 1 for i, d in enumerate(rr.get("ranked", []))}
        found = sorted(ranks[d] for d in gold_docs if d in ranks)
        if r["unanswerable"] and not r["abstained"]:
            reason = (
                f"Answered a question whose answer is not in the corpus: relevance gate score "
                f"{rr.get('gate', 0):.2f} passed the {threshold:.2f} threshold because related documents exist "
                f"({', '.join(rr.get('ranked', [])[:2])}); the LLM then composed an answer from them."
            )
        elif not r["unanswerable"] and r["abstained"]:
            reason = (
                f"Wrongly abstained: gold document at rank {found[0]} but gate score {rr.get('gate', 0):.2f} "
                f"< threshold {threshold:.2f}."
                if found
                else "Abstained because no gold document was retrieved (top hits: "
                f"{', '.join(rr.get('ranked', [])[:3])})."
            )
        elif q["gold"] and rr.get("recall@5", 1) < 1:
            miss = [grp[0] for grp in q["gold"] if not any(g in rr.get("ranked", [])[:5] for g in grp)]
            reason = f"Retrieval miss: {', '.join(miss)} not in the top-5 (top hits: {', '.join(rr.get('ranked', [])[:3])})."
            if q["category"] == "conversational":
                reason += (
                    " The follow-up depends on history that the condensed query did not fully carry over."
                )
            if q["category"] == "filter":
                reason += f" List question needs {len(q['gold'])} documents; the context window holds only the top passages."
        elif r["correctness"] is not None and r["correctness"] < 1:
            reason = (
                f"Gold document retrieved (rank {found[0] if found else '-'}), but the answer lacks: "
                f"{', '.join(r['missing_facts'])}."
            )
            if q["category"] == "ocr":
                reason += (
                    " The value exists only in the scan; OCR text or title-block parsing may have misread it."
                )
            if r["unsupported"]:
                reason += f" NLI flagged {r['unsupported']} unsupported sentence(s)."
        else:
            continue
        cands.append(
            {
                "id": r["id"],
                "category": q["category"],
                "question": q["question"],
                "expected": q["reference_answer"],
                "got": r["answer"][:400],
                "reason": reason,
            }
        )
    picked, seen = [], set()
    for c in cands:  # diverse categories first
        if c["category"] not in seen:
            picked.append(c)
            seen.add(c["category"])
    picked += [c for c in cands if c not in picked]
    return picked[:n]


# ------------------------------------------------------------------ orchestration
def run(
    skip_ablations: bool = False,
    gen_limit: int | None = None,
    gen: bool = True,
    ocr_eval: bool = True,
    provider: str | None = None,
    log=print,
) -> dict:
    from yokoten.db import init_db
    from yokoten.retrieval.index import get_index

    init_db()
    t_start = time.perf_counter()
    base = load_runtime().model_copy(
        update={"use_verified": False}
    )  # demo-time SME answers must not leak into eval
    if provider:
        base = base.model_copy(update={"llm_provider": provider, "llm_model": ""})
    dev, test = load_golden("dev"), load_golden("test")
    golden = {q["id"]: q for q in dev + test}
    log(f"golden set: dev {len(dev)}, test {len(test)}")

    # 1. retrieval ablations (no LLM); greedy tuning on dev
    if skip_ablations:
        chosen, ablations = base, []
    else:
        log("retrieval ablations:")
        chosen, ablations = run_ablations(base, dev, test, log)

    # 2. calibrate the abstention gate on dev (answerable vs unanswerable)
    dev_rows = run_retrieval(chosen, dev)
    cal = calibrate_threshold(
        [r["gate"] for r in dev_rows], [golden[r["id"]]["category"] == "unanswerable" for r in dev_rows]
    )
    th = cal["threshold"]
    chosen = chosen.model_copy(update={"abstain_threshold": th})
    log(
        f"abstention threshold (dev): {th} (answerable kept {cal['answerable_retention']:.3f}, "
        f"unanswerable caught {cal['unanswerable_recall']:.3f})"
    )

    # 3. final retrieval numbers on test with the chosen config
    test_rows = run_retrieval(chosen, test)
    ret = summarize_retrieval(test_rows)
    ret_abst = abstention_scores(
        [not r["passed"] for r in test_rows],
        [golden[r["id"]]["category"] == "unanswerable" for r in test_rows],
    )

    # 4. generation on the top configurations (test split)
    gen_configs, failures, sql_exp = [], [], {}
    gen_questions = stratified(test, gen_limit)
    provider_used, model_used = llm.resolve(chosen.llm_provider, chosen.llm_model)
    judge_used = _judge_provider(provider_used)
    if gen:
        variants = [
            ("chosen + prompt v2", chosen.model_copy(update={"prompt_version": "v2"})),
            ("chosen + prompt v1", chosen.model_copy(update={"prompt_version": "v1"})),
            (
                "naive RAG (dense, no rerank, no rewrite)",
                chosen.model_copy(
                    update={
                        "retrieval_mode": "dense",
                        "reranker": False,
                        "query_rewrite": False,
                        "use_filters": False,
                        "prompt_version": "v1",
                    }
                ),
            ),
        ]
        for name, cfg in variants:
            log(f"generation: {name} on {len(gen_questions)} test questions ({provider_used}/{model_used})")
            rows = run_generation(cfg, gen_questions, log)
            s = summarize_generation(rows)
            gen_configs.append(
                {
                    "name": name,
                    "provider": provider_used,
                    "model": model_used,
                    "prompt_version": cfg.prompt_version,
                    "n": len(rows),
                    **s,
                    "rows": rows,
                }
            )
        # K: analytical questions with the text-to-SQL route on vs off (all splits: only 8 such questions exist)
        analytical = [q for q in dev + test if q["category"] == "analytical"]
        sql_exp = {}
        for name, flag in (("sql_on", True), ("sql_off", False)):
            rows = run_generation(chosen.model_copy(update={"sql_route": flag}), analytical, log)
            sql_exp[name] = {
                "correctness": mean(r["correctness"] for r in rows),
                "n": len(rows),
                "rows": [{k: r[k] for k in ("id", "answer", "correctness")} for r in rows],
            }
        failures = explain_failures(gen_configs[0]["rows"], {r["id"]: r for r in test_rows}, golden, th)

    public = run_public(chosen)

    # 5. OCR engines
    ocr_res = run_ocr(["tesseract", "easyocr"], log) if ocr_eval else {}

    # 6. system metrics
    stage_lat = defaultdict(list)
    for r in test_rows:
        for k, v in r["stages"].items():
            stage_lat[k].append(v)
    for g in gen_configs[:1]:
        for r in g["rows"]:
            for k, v in (r.get("stages") or {}).items():
                if k in ("context", "generate", "verify"):
                    stage_lat[k].append(v)
    latency = {k: {"p50": pct(v, 50), "p95": pct(v, 95)} for k, v in stage_lat.items() if k in STAGES}
    index = get_index(chosen.chunking, chosen.embedding_model, chosen.collections)
    index.faiss_index("flat")
    index.faiss_index("hnsw")
    index.chroma()
    chroma_bytes = sum(p.stat().st_size for p in (settings.var_dir / "chroma").rglob("*") if p.is_file())
    system = {
        "latency": latency,
        "tokens_per_answer": {
            "input": gen_configs[0]["metrics"]["input_tokens"] if gen_configs else None,
            "output": gen_configs[0]["metrics"]["output_tokens"] if gen_configs else None,
        },
        "index": {
            "chunks_indexed": index.stats["chunks"],
            "embedding_dim": index.stats["dim"],
            "embed_all_chunks_s": index.stats["embed_s"],
            "faiss_flat_build_s": index.stats.get("faiss_flat_build_s"),
            "faiss_hnsw_build_s": index.stats.get("faiss_hnsw_build_s"),
            "faiss_flat_mb": round(index.stats.get("faiss_flat_bytes", 0) / 1e6, 2),
            "faiss_hnsw_mb": round(index.stats.get("faiss_hnsw_bytes", 0) / 1e6, 2),
            "chroma_mb": round(chroma_bytes / 1e6, 2),
            "bm25_build_s": index.stats["bm25_s"],
        },
    }

    main = gen_configs[0]["metrics"] if gen_configs else {}
    headline = [
        {
            "label": "Retrieval Recall@5",
            "value": ret["overall"]["recall@5"],
            "format": "pct",
            "hint": "Share of question hops whose gold document is in the top 5 (test split)",
        },
        {
            "label": "MRR",
            "value": ret["overall"]["mrr"],
            "format": "pct",
            "hint": "Mean reciprocal rank of the first gold doc",
        },
        {
            "label": "Answer correctness",
            "value": main.get("correctness"),
            "format": "pct",
            "hint": "Share of reference facts present in the answer (answerable test questions)",
        },
        {
            "label": "Faithfulness (NLI)",
            "value": main.get("faithfulness"),
            "format": "pct",
            "hint": "Share of answer sentences entailed by the cited passages",
        },
        {
            "label": "Abstention recall",
            "value": main.get("abstention_recall", ret_abst["abstention_recall"]),
            "format": "pct",
            "hint": "Unanswerable questions correctly declined",
        },
        {
            "label": "Hallucination rate",
            "value": main.get("hallucination_rate"),
            "format": "pct",
            "hint": "Answered questions with at least one unsupported sentence (or answering an unanswerable one)",
        },
        {
            "label": "Retrieval p50 latency",
            "value": pct([r["latency_ms"] for r in test_rows], 50),
            "format": "ms",
            "hint": "Query understanding + hybrid retrieval + rerank, CPU",
        },
        {
            "label": "Answer p50 latency",
            "value": main.get("latency_p50_ms"),
            "format": "ms",
            "hint": f"End-to-end with {provider_used}/{model_used}",
        },
    ]
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    result = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "split": "test",
        "n_questions": len(test),
        "n_dev": len(dev),
        "config": chosen.model_dump(),
        "headline": headline,
        "retrieval": {
            **ret,
            "abstention_gate": ret_abst,
            "threshold": th,
            "calibration": cal,
            "ablations": ablations,
            "rows": test_rows,
        },
        "generation": {
            "configs": gen_configs,
            "judge": "/".join(judge_used) if judge_used else None,
            "n_questions": len(gen_questions),
            "note": "" if gen else "Generation was skipped in this run.",
        },
        "system": system,
        "ocr": {
            "engines": ocr_res,
            "note": "Field accuracy on the 18 scans vs generator ground "
            "truth (part no, revision, material, lot, decision, "
            "measured values).",
        }
        if ocr_res
        else None,
        "failures": failures,
        "public": public,
        "sql_experiment": sql_exp,
        "duration_s": round(time.perf_counter() - t_start, 1),
        "hardware": {"device": device()},
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{run_id}.json").write_text(json.dumps(result, indent=1, default=str), "utf-8")
    (RESULTS / "latest.json").write_text(json.dumps(result, indent=1, default=str), "utf-8")
    _save_db(result)
    return result


def _save_db(result: dict) -> None:
    from yokoten.db import EvalRun, session

    with session() as s:
        s.merge(
            EvalRun(
                id=result["run_id"],
                summary={
                    "headline": result["headline"],
                    "config": result["config"],
                    "duration_s": result["duration_s"],
                },
                path=str(Path("eval/results") / f"{result['run_id']}.json"),
            )
        )
        s.commit()
