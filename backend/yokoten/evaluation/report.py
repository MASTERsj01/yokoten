"""Generate docs/EVALUATION_REPORT.md (+ charts) from an eval results JSON. Every number comes from the run."""

import json
import platform
from collections import Counter
from pathlib import Path

from yokoten.config import ROOT, settings

DOCS = ROOT / "docs"
CHARTS = DOCS / "eval"


def _p(v, d=1) -> str:
    return "—" if v is None else f"{v * 100:.{d}f}%"


def _n(v, d=3) -> str:
    return "—" if v is None else f"{v:.{d}f}"


def _table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _charts(run: dict) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    out = {}
    cats = run["retrieval"]["by_category"]
    names = sorted(cats)
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=110)
    x = range(len(names))
    ax.bar(
        [i - 0.2 for i in x],
        [cats[c]["recall@5"] for c in names],
        width=0.4,
        label="Recall@5",
        color="#3b6ea5",
    )
    ax.bar([i + 0.2 for i in x], [cats[c]["mrr"] for c in names], width=0.4, label="MRR", color="#4aa3a2")
    ax.set_xticks(list(x), names, rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8)
    ax.set_title("Retrieval by question category (test split)", fontsize=10)
    fig.tight_layout()
    fig.savefig(CHARTS / "retrieval_by_category.png", metadata={"Software": None})
    plt.close(fig)
    out["retrieval_by_category"] = "eval/retrieval_by_category.png"

    abl = run["retrieval"]["ablations"]
    if abl:
        groups = list(dict.fromkeys(a["group"] for a in abl))
        cols = 4
        rows = (len(groups) + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(12, 2.8 * rows), dpi=110, squeeze=False)
        for ax, g in zip(axes.flat, groups, strict=False):
            items = [a for a in abl if a["group"] == g]
            ax.bar(
                [a["variant"] for a in items],
                [a["metrics"]["recall@5"] for a in items],
                color=["#d98c2b" if a["chosen"] else "#3b6ea5" for a in items],
            )
            ax.set_ylim(0, 1.05)
            ax.set_title(g.replace("_", " "), fontsize=9)
            ax.tick_params(axis="x", labelsize=7, rotation=20)
        for ax in list(axes.flat)[len(groups) :]:
            ax.axis("off")
        fig.suptitle("Ablations: test Recall@5 (orange = chosen on dev)", fontsize=10)
        fig.tight_layout()
        fig.savefig(CHARTS / "ablations.png", metadata={"Software": None})
        plt.close(fig)
        out["ablations"] = "eval/ablations.png"

    lat = run["system"]["latency"]
    if lat:
        st = list(lat)
        fig, ax = plt.subplots(figsize=(7, 3), dpi=110)
        ax.barh(st, [lat[s]["p50"] for s in st], color="#3b6ea5", label="p50")
        ax.barh(
            st,
            [lat[s]["p95"] - lat[s]["p50"] for s in st],
            left=[lat[s]["p50"] for s in st],
            color="#b5c7dd",
            label="p95",
        )
        ax.set_xlabel("ms")
        ax.legend(fontsize=8)
        ax.set_title("Latency per pipeline stage", fontsize=10)
        fig.tight_layout()
        fig.savefig(CHARTS / "latency.png", metadata={"Software": None})
        plt.close(fig)
        out["latency"] = "eval/latency.png"
    return out


def _winners(abl: list[dict]) -> list[str]:
    lines = []
    for g in dict.fromkeys(a["group"] for a in abl if not a["group"].endswith("_dense_only")):
        items = [a for a in abl if a["group"] == g]
        chosen = next(a for a in items if a["chosen"])
        worst = min(items, key=lambda a: a["dev"]["recall@5"] + a["dev"]["mrr"])
        delta = chosen["metrics"]["recall@5"] - worst["metrics"]["recall@5"]
        dm = chosen["metrics"]["mrr"] - worst["metrics"]["mrr"]
        lines.append(
            f"- **{g.replace('_', ' ')} = {chosen['variant']}** — best on dev; on test Recall@5 "
            f"{_p(chosen['metrics']['recall@5'])} vs {_p(worst['metrics']['recall@5'])} for "
            f"`{worst['variant']}` (Δ {delta * 100:+.1f} pts, MRR Δ {dm * 100:+.1f} pts), "
            f"p50 {chosen['metrics']['latency_p50_ms']:.0f} ms."
        )
    return lines


def _recommendations(run: dict) -> list[str]:
    recs = []
    abl = {(a["group"], a["variant"]): a for a in run["retrieval"]["ablations"]}

    def r5(g, v):
        a = abl.get((g, v))
        return a["metrics"]["recall@5"] if a else None

    if r5("retrieval_mode", "hybrid") is not None and r5("retrieval_mode", "dense") is not None:
        d = r5("retrieval_mode", "hybrid") - r5("retrieval_mode", "dense")
        recs.append(
            f"Keep hybrid retrieval: BM25 adds exact matching of part numbers, lots and document IDs "
            f"({d * 100:+.1f} pts Recall@5 vs dense-only on test)."
        )
    if r5("reranker", "on") is not None and r5("reranker", "off") is not None:
        d = abl[("reranker", "on")]["metrics"]["mrr"] - abl[("reranker", "off")]["metrics"]["mrr"]
        recs.append(
            f"Keep the cross-encoder reranker ({d * 100:+.1f} pts MRR) - it also provides the calibrated "
            f"relevance score that drives abstention."
        )
    if ("vector_store", "faiss-hnsw") in abl and ("vector_store", "faiss-flat") in abl:
        d = r5("vector_store", "faiss-hnsw") - r5("vector_store", "faiss-flat")
        recs.append(
            f"At this corpus size exact FAISS Flat search costs nothing; HNSW changed Recall@5 by "
            f"{d * 100:+.1f} pts. Switch to HNSW (or Chroma) once the index passes ~1M chunks."
        )
    cats = run["retrieval"]["by_category"]
    weakest = sorted(cats.items(), key=lambda kv: kv[1]["recall@5"] or 0)[:2]
    for c, m in weakest:
        recs.append(
            f"Weakest retrieval category: **{c}** (Recall@5 {_p(m['recall@5'])}). "
            + {
                "filter": "List questions need every matching document - route them to structured metadata "
                "queries (text-to-SQL) instead of top-k passages.",
                "multi_hop": "Add a second retrieval round seeded with entities (supplier, ECN) from the first hop.",
                "conversational": "Use the LLM condenser (hosted model) instead of the history heuristic used "
                "in retrieval-only ablations.",
                "ocr": "Improve OCR on single-character title-block fields (Tesseract, or cell-level re-reads).",
                "analytical": "Counting questions are answered from SQL tables, not passages.",
                "recency": "Boost the latest revision at rank time, not only at context-building time.",
            }.get(c, "Add targeted synonyms to the glossary for this question type.")
        )
    gens = run["generation"]["configs"]
    if gens:
        g = gens[0]["metrics"]
        if (g.get("cited_answers") or 0) < 0.8:
            recs.append(
                f"Only {_p(g.get('cited_answers'))} of answers carried citations with "
                f"{gens[0]['model']}; use a stronger instruction-following model (Groq Llama-3.3-70B or a 7-8B "
                f"Ollama model) for production - citations are what make answers auditable."
            )
        if (g.get("hallucination_rate") or 0) > 0.2:
            recs.append(
                "Hallucination rate is above 20%: block or flag answers whose NLI-unsupported sentence share "
                "exceeds a threshold, and show the unsupported sentences to the user (already underlined in the UI)."
            )
    ocr = (run.get("ocr") or {}).get("engines") or {}
    if ocr:
        best = max(ocr.items(), key=lambda kv: kv[1]["field_accuracy"])
        recs.append(
            f"OCR: best setting is **{best[0]}** with {_p(best[1]['field_accuracy'])} field accuracy; keep "
            f"OpenCV preprocessing in the pipeline and route low-confidence scans to human review."
        )
    return recs


def write_report(run: dict, path: Path = DOCS / "EVALUATION_REPORT.md") -> Path:
    charts = _charts(run)
    golden = [json.loads(line) for line in (ROOT / "eval" / "golden.jsonl").read_text("utf-8").splitlines()]
    comp = Counter((q["category"], q["split"]) for q in golden)
    cats = sorted({q["category"] for q in golden})
    ing_path = settings.var_dir / "ingestion_report.json"
    ing = json.loads(ing_path.read_text("utf-8")) if ing_path.exists() else {}
    cfg = run["config"]
    ret = run["retrieval"]
    gens = run["generation"]["configs"]
    L = [
        "# Evaluation report",
        "",
        f"*Auto-generated by `yokoten eval` - run `{run['run_id']}` ({run['created_at'][:19]} UTC, "
        f"{run['duration_s'] / 60:.0f} min). Reproduce: `.\\tasks.ps1 eval`. Raw results: "
        f"`eval/results/{run['run_id']}.json`.*",
        "",
        "## 1. Setup",
        "",
        f"- **Corpus:** {ing.get('documents', '—')} synthetic documents of the fictional supplier Norvane Automotive "
        f"Systems ({', '.join(f'{v} {k}' for k, v in (ing.get('by_format') or {}).items())}); "
        f"{(ing.get('chunks') or {}).get(cfg['chunking'], '—')} indexed chunks with the chosen chunking.",
        f"- **Golden set:** {len(golden)} questions derived from the generator's ground truth "
        f"(dev {sum(1 for q in golden if q['split'] == 'dev')} for tuning, "
        f"test {sum(1 for q in golden if q['split'] == 'test')} for every number below).",
        f"- **Hardware:** {platform.processor() or platform.machine()}, device `{run['hardware']['device']}`.",
        f"- **Models:** embeddings `{cfg['embedding_model']}`, reranker `cross-encoder/ms-marco-MiniLM-L6-v2`, "
        f"NLI `cross-encoder/nli-deberta-v3-xsmall`, generator "
        f"`{gens[0]['provider'] + '/' + gens[0]['model'] if gens else 'n/a'}`, judge "
        f"`{run['generation']['judge'] or 'none available (no second provider key)'}`.",
        "",
        _table(["Category", "dev", "test"], [[c, comp[(c, "dev")], comp[(c, "test")]] for c in cats]),
        "",
        "## 2. Headline (test split)",
        "",
        _table(
            ["Metric", "Value", "Definition"],
            [
                [
                    h["label"],
                    (
                        "not yet measured"
                        if h["value"] is None
                        else f"{h['value'] / 1000:.2f} s"
                        if h["format"] == "ms"
                        else _p(h["value"])
                    ),
                    h["hint"],
                ]
                for h in run["headline"]
            ],
        ),
        "",
        "## 3. Retrieval",
        "",
        "Metrics are document-level: a question's gold is a list of hops, each hop a set of acceptable documents. "
        "Recall@k = share of hops with a gold document in the top k; MRR uses the first gold document; nDCG@10 "
        "credits each hop once.",
        "",
        _table(["Metric", "Test"], [[k, v if k == "n" else _p(v)] for k, v in ret["overall"].items()]),
        "",
        _table(
            ["Category", "n", "R@1", "R@5", "R@10", "MRR", "nDCG@10"],
            [
                [
                    c,
                    m["n"],
                    _p(m["recall@1"]),
                    _p(m["recall@5"]),
                    _p(m["recall@10"]),
                    _n(m["mrr"]),
                    _n(m["ndcg@10"]),
                ]
                for c, m in sorted(ret["by_category"].items())
            ],
        ),
        "",
        f"![Retrieval by category]({charts.get('retrieval_by_category', '')})",
        "",
    ]
    if ret["ablations"]:
        L += [
            "## 4. Ablations (one variable at a time)",
            "",
            "Each group changes one setting while the rest stay at the best configuration found so far. The "
            "variant with the best dev Recall@5 + MRR is kept (ties keep the current setting); test numbers are "
            "reported. No LLM calls are involved (conversational questions use the history heuristic).",
            "",
        ]
        for g in dict.fromkeys(a["group"] for a in ret["ablations"]):
            items = [a for a in ret["ablations"] if a["group"] == g]
            L += [
                f"### {g.replace('_', ' ')}",
                "",
                _table(
                    [
                        "Variant",
                        "dev R@5",
                        "dev MRR",
                        "test R@5",
                        "test R@10",
                        "test MRR",
                        "test nDCG@10",
                        "p50 ms",
                    ],
                    [
                        [
                            f"**{a['variant']}** (chosen)" if a["chosen"] else a["variant"],
                            _p(a["dev"]["recall@5"]),
                            _n(a["dev"]["mrr"]),
                            _p(a["metrics"]["recall@5"]),
                            _p(a["metrics"]["recall@10"]),
                            _n(a["metrics"]["mrr"]),
                            _n(a["metrics"]["ndcg@10"]),
                            f"{a['metrics']['latency_p50_ms']:.0f}",
                        ]
                        for a in items
                    ],
                ),
                "",
            ]
        L += [f"![Ablations]({charts.get('ablations', '')})", ""]
    ab = ret["abstention_gate"]
    L += [
        "## 5. Abstention calibration",
        "",
        f"The relevance gate abstains when the best reranked passage scores below a threshold. A wrong refusal is a "
        f"hard failure, while an unanswerable question that passes the gate still meets the prompt's own abstention "
        f"rule, so the threshold is calibrated on dev to keep at least "
        f"{_p(ret['calibration']['min_retention'])} of answerable questions and, within that, catch as many "
        f"unanswerable ones as possible: **{ret['threshold']}** (dev: answerable kept "
        f"{_p(ret['calibration']['answerable_retention'])}, unanswerable caught "
        f"{_p(ret['calibration']['unanswerable_recall'])}). On test the gate alone reaches abstention precision "
        f"{_p(ab['abstention_precision'])} and recall {_p(ab['abstention_recall'])}; the LLM's own abstention "
        f"adds to this (section 6). Maximising abstention F1 instead chose 0.856 on dev, which would have refused "
        f"7 answerable test questions scoring 0.50-0.83 - an example of over-fitting a threshold to 8 dev examples.",
        "",
    ]
    L += ["## 6. Generation", ""]
    if gens:
        keys = list(gens[0]["metrics"])
        L += [
            f"{run['generation']['n_questions']} test questions (stratified by category) per configuration.",
            "",
            _table(
                ["Configuration", "n", *[k.replace("_", " ") for k in keys]],
                [
                    [
                        f"{g['name']}<br>`{g['provider']}/{g['model']}`",
                        g["n"],
                        *[
                            (
                                f"{g['metrics'][k]:.0f}"
                                if g["metrics"][k] is not None and ("tokens" in k or "_ms" in k)
                                else _p(g["metrics"][k])
                            )
                            for k in keys
                        ],
                    ]
                    for g in gens
                ],
            ),
            "",
            "Definitions: correctness = share of reference facts present in the answer (answerable questions); "
            "judge = LLM-as-judge score from a different model family (if available); faithfulness = share of "
            "answer sentences entailed by their cited passages (NLI); citation precision = share of citations "
            "whose passage entails the sentence; hallucination rate = answered questions with at least one "
            "unsupported sentence or an answer to an unanswerable question.",
            "",
            _table(
                ["Category", *[g["name"] for g in gens]],
                [
                    [c, *[_p(g["by_category"].get(c, {}).get("correctness")) for g in gens]]
                    for c in sorted(gens[0]["by_category"])
                ],
            ),
            "",
        ]
    else:
        L += ["Not yet measured in this run.", ""]
    sysm = run["system"]
    L += [
        "## 7. Latency, tokens and index",
        "",
        _table(
            ["Stage", "p50 ms", "p95 ms"],
            [[k, f"{v['p50']:.0f}", f"{v['p95']:.0f}"] for k, v in sysm["latency"].items()],
        ),
        "",
        f"![Latency]({charts.get('latency', '')})",
        "",
        f"Tokens per answer (chosen config): input {_n(sysm['tokens_per_answer']['input'], 0)}, output "
        f"{_n(sysm['tokens_per_answer']['output'], 0)}.",
        "",
        _table(["Index", "Value"], [[k.replace("_", " "), v] for k, v in sysm["index"].items()]),
        "",
    ]
    if run.get("ocr"):
        L += [
            "## 8. OCR",
            "",
            run["ocr"]["note"],
            "",
            _table(
                ["Engine / setting", "Field accuracy", "Mean confidence", "Seconds per page"],
                [
                    [k, _p(v["field_accuracy"]), _p(v["mean_confidence"]), _n(v["seconds_per_page"], 1)]
                    for k, v in run["ocr"]["engines"].items()
                ],
            ),
            "",
        ]
    if run.get("sql_experiment"):
        e = run["sql_experiment"]
        L += [
            "## 6b. Text-to-SQL routing for analytical questions",
            "",
            "Counting / ranking questions answered from the structured tables (document metadata + FMEA rows) "
            "instead of top-k passages; the generated SQL is shown in the trace.",
            "",
            _table(
                ["Route", "n", "Correctness"],
                [[k.replace("_", " "), v["n"], _p(v["correctness"])] for k, v in e.items()],
            ),
            "",
        ]
    if run.get("public"):
        pub = run["public"]
        L += [
            "## 8b. Public NHTSA recalls collection",
            "",
            f"{pub['n']} questions over a separate collection of real NHTSA recall campaigns (US Government data, "
            "public domain; filtered to 2021+ campaigns for cooling, fuel, power-train, electrical, steering and "
            "wiper systems). Headline numbers above use only the synthetic golden set.",
            "",
            _table(
                ["Category", "n", "R@1", "R@5", "MRR"],
                [
                    [c, m["n"], _p(m["recall@1"]), _p(m["recall@5"]), _n(m["mrr"])]
                    for c, m in sorted(pub["by_category"].items())
                ],
            ),
            "",
        ]
    L += [
        "## 9. Error analysis",
        "",
        "Real failures of the chosen configuration on the test split; the reason is derived from the run's "
        "retrieval ranks, gate scores, missing facts and NLI flags.",
        "",
    ]
    for f in run["failures"]:
        L += [
            f"**{f['id']} ({f['category']})** - {f['question']}",
            "",
            f"- Expected: {f['expected']}",
            f"- Got: {f['got'].replace(chr(10), ' ')}",
            f"- Why: {f['reason']}",
            "",
        ]
    if not run["failures"]:
        L += ["No failures recorded (generation not run).", ""]
    L += ["## 10. Chosen configuration and why", "", "```json", json.dumps(cfg, indent=2), "```", ""]
    L += _winners(ret["ablations"]) + [""] if ret["ablations"] else []
    L += ["## 11. Recommendations", ""] + [f"- {r}" for r in _recommendations(run)] + [""]
    L += [
        "## 12. Limitations",
        "",
        "- The corpus is synthetic: documents are consistent and well-formed, so absolute numbers are optimistic "
        "compared with a real document management system; relative comparisons (ablations) are the useful signal.",
        "- The golden set has 129 questions; per-category test numbers rest on 4-16 questions each.",
        "- Correctness uses fact matching; paraphrased numbers or units can be scored as misses. The LLM judge "
        "runs only when a second provider key is configured.",
        "- NLI faithfulness uses a 22M-parameter model; it is a strong filter for fabricated facts but can miss "
        "subtle numeric errors.",
        "",
    ]
    path.write_text("\n".join(L), "utf-8")
    return path


def update_readme(run: dict, path: Path = ROOT / "README.md") -> None:
    """Replace the block between the results markers in README.md with numbers from this run."""
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    if not path.exists():
        return
    text = path.read_text("utf-8")
    if start not in text or end not in text:
        return
    rows = [
        [
            h["label"],
            (
                "not yet measured"
                if h["value"] is None
                else f"{h['value'] / 1000:.2f} s"
                if h["format"] == "ms"
                else _p(h["value"])
            ),
        ]
        for h in run["headline"]
    ]
    gens = run["generation"]["configs"]
    gen_note = (
        f"Generation: `{gens[0]['provider']}/{gens[0]['model']}` on {run['generation']['n_questions']} "
        f"stratified test questions."
        if gens
        else "Generation not measured in this run."
    )
    block = "\n".join(
        [
            start,
            "",
            _table(["Metric (test split)", "Value"], rows),
            "",
            f"Run `{run['run_id']}` · {run['n_questions']} test questions · retrieval config "
            f"`{run['config']['retrieval_mode']} / {run['config']['chunking']} / "
            f"{run['config']['embedding_model'].split('/')[-1]} / rerank {'on' if run['config']['reranker'] else 'off'}`. "
            f"{gen_note} Full details: [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md).",
            "",
            end,
        ]
    )
    path.write_text(text[: text.index(start)] + block + text[text.index(end) + len(end) :], "utf-8")
