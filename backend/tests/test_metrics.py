import pytest

from yokoten.evaluation.harness import stratified
from yokoten.evaluation.metrics import (
    abstention_scores,
    calibrate_threshold,
    doc_ranking,
    fact_present,
    fact_score,
    mrr,
    ndcg_at_k,
    recall_at_k,
)


def test_ranking_and_hop_metrics():
    ranked = doc_ranking(["A", "A", "X", "SQR", "B"])
    assert ranked == ["A", "X", "SQR", "B"]
    groups = [["A", "LL-A"], ["SQR"]]  # two hops, the first with an alternative document
    assert recall_at_k(ranked, groups, 1) == 0.5
    assert recall_at_k(ranked, groups, 3) == 1.0
    assert mrr(["X", "LL-A"], groups) == 0.5
    assert ndcg_at_k(["A", "SQR"], groups) == pytest.approx(1.0)
    assert 0 < ndcg_at_k(["X", "A", "SQR"], groups) < 1


def test_fact_matching():
    assert fact_present("Compression set rose to 38 % after 1,000 h", "38")
    assert fact_present("The PPM was 1500.", "1,500".replace(",", ""))
    assert fact_present("Speed of 1,500 rpm", "1500")
    assert not fact_present("the 2019 report", "9")  # word boundaries
    assert fact_present("AP is High", "high|AP H")
    assert fact_score("voids and belt speed", ["brazing voids", "belt speed"]) == 0.5
    assert fact_score("anything", []) is None


def test_abstention_and_threshold():
    s = abstention_scores([True, False, True], [True, False, False])
    assert s["abstention_precision"] == 0.5 and s["abstention_recall"] == 1.0
    c = calibrate_threshold([0.05, 0.1, 0.9, 0.8, 0.3], [True, True, False, False, False])
    assert 0.1 < c["threshold"] < 0.3 and c["unanswerable_recall"] == 1.0 and c["answerable_retention"] == 1.0
    # a near-miss unanswerable (0.85) must not push the gate above answerable questions
    c = calibrate_threshold([0.05, 0.85, 0.9, 0.6, 0.95], [True, True, False, False, False])
    assert c["threshold"] < 0.6


def test_stratified_subset_covers_categories():
    qs = [{"category": c, "id": f"{c}{i}"} for c in "abc" for i in range(5)]
    sub = stratified(qs, 6)
    assert len(sub) == 6 and {q["category"] for q in sub} == {"a", "b", "c"}
