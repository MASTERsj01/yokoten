"""Evaluation metrics. Retrieval gold = groups of acceptable doc IDs (one group per hop)."""

import math
import re

import numpy as np


def doc_ranking(doc_ids: list[str]) -> list[str]:
    """Chunk-level ranking -> unique doc IDs in first-seen order."""
    seen, out = set(), []
    for d in doc_ids:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def recall_at_k(ranked: list[str], groups: list[list[str]], k: int) -> float:
    top = set(ranked[:k])
    return sum(any(g in top for g in grp) for grp in groups) / len(groups)


def mrr(ranked: list[str], groups: list[list[str]]) -> float:
    gold = {g for grp in groups for g in grp}
    return next((1 / (i + 1) for i, d in enumerate(ranked) if d in gold), 0.0)


def ndcg_at_k(ranked: list[str], groups: list[list[str]], k: int = 10) -> float:
    """Each hop (group) earns gain once, at the rank of its first retrieved member."""
    credited: set[int] = set()
    dcg = 0.0
    for i, d in enumerate(ranked[:k]):
        for gi, grp in enumerate(groups):
            if gi not in credited and d in grp:
                credited.add(gi)
                dcg += 1 / math.log2(i + 2)
                break
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(groups), k)))
    return dcg / idcg if idcg else 0.0


def retrieval_metrics(ranked: list[str], groups: list[list[str]]) -> dict:
    return {
        "recall@1": recall_at_k(ranked, groups, 1),
        "recall@3": recall_at_k(ranked, groups, 3),
        "recall@5": recall_at_k(ranked, groups, 5),
        "recall@10": recall_at_k(ranked, groups, 10),
        "mrr": mrr(ranked, groups),
        "ndcg@10": ndcg_at_k(ranked, groups, 10),
    }


def _norm(text: str) -> str:
    text = text.lower().replace("–", "-").replace("‑", "-")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,500 -> 1500
    return re.sub(r"\s+", " ", text)


def fact_present(answer: str, fact: str) -> bool:
    """A fact may list alternatives separated by '|'; matched on word boundaries, case-insensitive."""
    a = _norm(answer)
    for alt in fact.split("|"):
        alt = _norm(alt.strip())
        if alt and re.search(rf"(?<![\w.]){re.escape(alt)}(?![\w])", a):
            return True
    return False


def fact_score(answer: str, facts: list[str]) -> float | None:
    if not facts:
        return None
    return sum(fact_present(answer, f) for f in facts) / len(facts)


def mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def pct(xs, q) -> float | None:
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def aggregate(rows: list[dict], keys: list[str]) -> dict:
    return {k: mean(r.get(k) for r in rows) for k in keys} | {"n": len(rows)}


def abstention_scores(pred: list[bool], gold: list[bool]) -> dict:
    tp = sum(p and g for p, g in zip(pred, gold, strict=True))
    fp = sum(p and not g for p, g in zip(pred, gold, strict=True))
    fn = sum(g and not p for p, g in zip(pred, gold, strict=True))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {"abstention_precision": precision, "abstention_recall": recall, "abstention_f1": f1}


def calibrate_threshold(scores: list[float], unanswerable: list[bool], min_retention: float = 0.975) -> dict:
    """Gate threshold (abstain when score < t). Wrongly refusing an answerable question is a hard failure while an
    unanswerable one that passes still meets the prompt's own abstention rule, so: keep >= min_retention of the
    answerable questions, maximise abstention on unanswerable ones, prefer higher retention, and put t in the middle
    of the score gap (margin)."""
    uniq = sorted(set(scores))
    cands = [0.0] + [(a + b) / 2 for a, b in zip(uniq, uniq[1:], strict=False)] + [uniq[-1] + 1e-6]
    n_ans = sum(not u for u in unanswerable) or 1
    n_un = sum(unanswerable) or 1
    best = None
    for t in cands:
        kept = sum(s >= t for s, u in zip(scores, unanswerable, strict=True) if not u) / n_ans
        caught = sum(s < t for s, u in zip(scores, unanswerable, strict=True) if u) / n_un
        if kept < min_retention:
            continue
        key = (caught, kept, -t)
        if best is None or key > best[0]:
            best = (key, t, kept, caught)
    _, t, kept, caught = best
    return {
        "threshold": round(t, 4),
        "answerable_retention": kept,
        "unanswerable_recall": caught,
        "min_retention": min_retention,
    }
