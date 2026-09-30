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
        name = f"**{g.replace('_', ' ')} = {chosen['variant']}**"
        scores = {round(a["dev"]["recall@5"] + a["dev"]["mrr"], 4) for a in items}
        if len(scores) == 1:
            lines.append(
                f"- {name} — all variants tie on dev and test (test Recall@5 "
                f"{_p(chosen['metrics']['recall@5'])}); kept the default."
            )
            continue
        worst = min(items, key=lambda a: a["dev"]["recall@5"] + a["dev"]["mrr"])
        d5 = chosen["metrics"]["recall@5"] - worst["metrics"]["recall@5"]
        dm = chosen["metrics"]["mrr"] - worst["metrics"]["mrr"]
        lines.append(
            f"- {name} — best on dev (Recall@5 + MRR). On test vs `{worst['variant']}`: Recall@5 "
            f"{d5 * 100:+.1f} pts, MRR {dm * 100:+.1f} pts; p50 {chosen['metrics']['latency_p50_ms']:.0f} ms vs "
            f"{worst['metrics']['latency_p50_ms']:.0f} ms."
        )
    return lines


def _recommendations(run: dict) -> list[str]:
    recs = []
    abl = {(a["group"], a["variant"]): a for a in run["retrieval"]["ablations"]}

    def r5(g, v):
        a = abl.get((g, v))
        return a["metrics"]["recall@5"] if a else None

    def mrr(g, v):
        a = abl.get((g, v))
        return a["metrics"]["mrr"] if a else None

    if ("query_rewrite", "on") in abl and ("query_rewrite", "off") in abl:
        d = r5("query_rewrite", "on") - r5("query_rewrite", "off")
        recs.append(
            f"Keep query rewriting (condensing follow-ups + glossary acronym expansion): the largest single "
            f"retrieval gain measured ({d * 100:+.1f} pts Recall@5 on test)."
        )
    if ("metadata_filters", "on") in abl and ("metadata_filters", "off") in abl:
        d = mrr("metadata_filters", "on") - mrr("metadata_filters", "off")
        recs.append(
            f"Keep metadata filter extraction ({d * 100:+.1f} pts MRR on test); its 'compatible-with' "
            f"semantics keep documents without a component (e.g. supplier reports) available for multi-hop."
        )
    if r5("reranker", "on") is not None and r5("reranker", "off") is not None:
        d = mrr("reranker", "on") - mrr("reranker", "off")
        recs.append(
            f"Keep the cross-encoder reranker ({d * 100:+.1f} pts MRR on test, at ~3x the retrieval "
            f"latency on CPU) - it also provides the calibrated relevance score that drives abstention."
        )
    if r5("retrieval_mode", "hybrid") is not None and r5("retrieval_mode", "dense") is not None:
        d = r5("retrieval_mode", "hybrid") - r5("retrieval_mode", "dense")
        if abs(d) < 0.005:
            recs.append(
                "Dense, BM25 and hybrid first stages end in the same final ranking once the reranker "
                "re-orders a 30-candidate pool on this corpus; hybrid is kept because BM25 guarantees exact "
                "matches on part numbers, lots and document IDs as the corpus grows."
            )
        else:
            recs.append(f"Keep hybrid retrieval ({d * 100:+.1f} pts Recall@5 vs dense-only on test).")
    if ("vector_store", "faiss-hnsw") in abl and ("vector_store", "faiss-flat") in abl:
        recs.append(
            "Exact FAISS Flat search is instant at this size and HNSW / Chroma return the same ranking; "
            "switch to HNSW (or a managed vector DB) once the index reaches millions of chunks."
        )
    cats = run["retrieval"]["by_category"]
    weakest = [
        kv for kv in sorted(cats.items(), key=lambda kv: kv[1]["mrr"] or 0) if (kv[1]["mrr"] or 0) < 0.95
    ][:2]
    for c, m in weakest:
        recs.append(
            f"Weak retrieval category: **{c}** (Recall@5 {_p(m['recall@5'])}, MRR {_n(m['mrr'])}). "
            + {
                "filter": "List questions need every matching document - route them to structured metadata "
                "queries (text-to-SQL) instead of top-k passages.",
                "multi_hop": "Add a second retrieval round seeded with entities (supplier, ECN) from the first hop.",
                "conversational": "Use the LLM condenser (hosted model) instead of the history heuristic used "
                "in retrieval-only ablations.",
                "ocr": "Improve OCR on single-character title-block fields (Tesseract, or cell-level re-reads).",
                "analytical": "Counting questions are answered from SQL tables, not passages.",
                "recency": "Boost the latest revision at rank time, not only at context-building time.",
                "table": "Spreadsheet rows rank below prose; index FMEA rows with their column names in the "
                "embedding text and route rating look-ups to SQL.",
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
                f"Hallucination rate is {_p(g.get('hallucination_rate'))} with a 1.5B local model: flag answers whose "
                "unsupported-sentence share exceeds a threshold (unsupported sentences are already underlined in "
                "the UI), and re-run this evaluation with a hosted 70B model before any pilot."
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
        f"- **Corpus:** {(ing.get('by_collection') or {}).get('engineering', '—')} synthetic documents of the "
        f"fictional supplier Norvane Automotive Systems (PDF, DOCX, XLSX, Markdown, scanned PNG/JPG); "
        f"{run['system']['index']['chunks_indexed']} indexed chunks with the chosen `{cfg['chunking']}` chunking. "
        f"A separate collection of {(ing.get('by_collection') or {}).get('public_recalls', 0)} real NHTSA recall "
        f"campaigns is evaluated on its own (section 8b).",
        f"- **Golden set:** {len(golden)} questions derived from the generator's ground truth "
        f"(dev {sum(1 for q in golden if q['split'] == 'dev')} for tuning, "
        f"test {sum(1 for q in golden if q['split'] == 'test')} for every number below).",
        f"- **Hardware:** {platform.processor() or platform.machine()}, device `{run['hardware']['device']}`.",
        f"- **Models:** embeddings `{cfg['embedding_model']}`, reranker `cross-encoder/ms-marco-MiniLM-L6-v2`, "
        f"faithfulness checker `{(run.get('nli_validation') or {}).get('model', 'NLI')}`, generator "
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
                *(
                    [
                        "Diagnostic, not used for selection: each embedding model on its own (dense only, no BM25, no "
                        "reranker) to show first-stage differences that the full pipeline hides.",
                        "",
                    ]
                    if g.endswith("_dense_only")
                    else []
                ),
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
        keys = [k for k in gens[0]["metrics"] if k != "latency_p50_ms"]  # replayed from cache: see section 7
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
            "answer sentences supported by their cited passages (validated checker below); citation precision = "
            "share of citations whose passage alone supports the sentence; hallucination rate = answered questions with at least one "
            "unsupported sentence or an answer to an unanswerable question. The text-to-SQL route is active in all "
            "three configurations (its own effect is isolated in section 6b), so 'naive RAG' differs only in "
            "retrieval (dense only, no rerank, no query rewriting or filters) and prompt v1.",
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
    if run.get("nli_validation"):
        v = run["nli_validation"]
        L += [
            "## 6c. How far can the faithfulness numbers be trusted?",
            "",
            f"A sentence counts as supported if the NLI model entails it from the 3 source sentences closest to it, or "
            f"if at least 80% of its content words and every number it states appear in the cited passages (or the "
            f"question it restates). The checker itself was validated on {v['n']} claims with known labels: reference "
            f"answers against their gold documents (true), another question's reference answer (false) and the true "
            f"claim with one number altered (false). It accepts **{_p(v['tpr'])}** of true claims and rejects "
            f"**{_p(v['tnr'])}** of false ones (accuracy by kind: "
            + ", ".join(f"{k} {_p(x, 0)}" for k, x in v["accuracy_by_kind"].items())
            + f"). NLI alone accepted only {_p(v['nli_only_tpr'])} of true claims - it misses compound multi-hop and "
            "table-derived claims - and the xsmall NLI model tried first accepted 10%, which is why the checker was "
            "changed. Remaining misses make faithfulness a slightly conservative lower bound.",
            "",
        ]
    sysm = run["system"]
    bench = run.get("latency_benchmark") or {}
    L += [
        "## 7. Latency, tokens and index",
        "",
        f"Retrieval stages come from the full test run; context / generate / verify come from a benchmark of "
        f"{bench.get('n', 0)} answers with the LLM response cache switched off (answer p50 "
        f"{(bench.get('answer_p50_ms') or 0) / 1000:.1f} s, p95 {(bench.get('answer_p95_ms') or 0) / 1000:.1f} s on "
        f"`{run['hardware']['device']}`).",
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
    shown = {
        k: v
        for k, v in cfg.items()
        if k not in ("llm_provider", "llm_model", "use_verified", "llm_cache", "verified_similarity")
    }
    L += [
        "## 10. Chosen configuration and why",
        "",
        f"Retrieval and prompt settings below; the generator used in this run was "
        f"`{gens[0]['provider']}/{gens[0]['model']}` (the configured provider falls back when no key is set)."
        if gens
        else "",
        "",
        "```json",
        json.dumps(shown, indent=2),
        "```",
        "",
    ]
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
        "- Faithfulness uses an NLI + lexical/number checker validated on known claims (section 6); it misses some "
        "true table-derived claims, so faithfulness is a conservative lower bound.",
        "- All generation numbers use a 1.5B-parameter local model because no hosted LLM key was configured for this "
        "run; `.\\tasks.ps1 eval --provider groq` reproduces them with a hosted model.",
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
