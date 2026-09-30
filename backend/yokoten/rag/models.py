"""Small Hugging Face models used directly (lazy-loaded, CPU-friendly).

- cross-encoder reranker (sentence-transformers CrossEncoder)
- NLI model (transformers AutoModelForSequenceClassification): sentence-level faithfulness + zero-shot intent
"""

import math
import re
from functools import cache

import numpy as np

from yokoten.config import device

RERANKER = "cross-encoder/ms-marco-MiniLM-L6-v2"
NLI_MODEL = "cross-encoder/nli-deberta-v3-base"  # chosen by validating checkers on known-true/false claims
FOCUS_MODEL = "BAAI/bge-small-en-v1.5"


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


@cache
def reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER, device=device(), max_length=512)


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    return [float(s) for s in reranker().predict([(query, p) for p in passages], batch_size=32)]


@cache
def _nli():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(NLI_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL).to(device()).eval()
    labels = {v.lower(): int(k) for k, v in model.config.id2label.items()}
    return tok, model, labels, torch


def nli_probs(pairs: list[tuple[str, str]], batch_size: int = 16) -> np.ndarray:
    """(premise, hypothesis) -> probabilities with columns [entailment, neutral, contradiction]."""
    if not pairs:
        return np.zeros((0, 3))
    tok, model, labels, torch = _nli()
    out = []
    for i in range(0, len(pairs), batch_size):
        batch = pairs[i : i + batch_size]
        enc = tok(
            [p for p, _ in batch],
            [h for _, h in batch],
            truncation="only_first",
            max_length=384,
            padding=True,
            return_tensors="pt",
        ).to(device())
        with torch.no_grad():
            probs = torch.softmax(model(**enc).logits, dim=-1).cpu().numpy()
        out.append(probs[:, [labels["entailment"], labels["neutral"], labels["contradiction"]]])
    return np.vstack(out)


_UNIT = re.compile(r"(?<=[.!?])\s+|\n+")


def focus_premise(premises: list[str], hypothesis: str, k: int = 3) -> str:
    """NLI models judge long passages poorly: keep the k source sentences closest to the claim (in source order)."""
    from yokoten.retrieval.embeddings import model as embedder

    units = [u.strip() for p in premises for u in _UNIT.split(p) if len(u.strip()) > 3]
    if len(units) <= k:
        return " ".join(units)
    v = embedder(FOCUS_MODEL).encode(units + [hypothesis], normalize_embeddings=True, convert_to_numpy=True)
    top = np.argsort(-(v[:-1] @ v[-1]))[:k]
    return " ".join(units[i] for i in sorted(top))


_STOP = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "which",
        "who",
        "why",
        "with",
        "did",
        "does",
        "do",
        "not",
        "no",
        "than",
        "then",
        "there",
        "these",
        "those",
        "their",
        "been",
        "being",
        "into",
        "over",
        "under",
        "after",
        "before",
        "about",
        "also",
        "more",
        "most",
        "per",
    ]
)
_WORD = re.compile(r"[a-z0-9][a-z0-9\-./]*")
_NUM = re.compile(r"\d+(?:\.\d+)?")
LEXICAL_SUPPORT = 0.8


def _content(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def support(premises: list[str], claim: str, question: str = "") -> dict:
    """Is the claim supported by the passages? NLI entailment on the closest source sentences, OR lexical support:
    >= 80% of the claim's content words appear in the passages (or the question it restates) AND every number in
    the claim appears there. Validated on known-true / known-false / number-altered claims in the eval."""
    ent, contra = entailment(premises, claim)
    given = " ".join(premises) + " " + question
    words = _content(claim)
    have = set(_content(given))
    lexical = sum(w in have for w in words) / len(words) if words else 0.0
    numbers_ok = set(_NUM.findall(claim.replace(",", ""))) <= set(_NUM.findall(given.replace(",", "")))
    by_lexical = lexical >= LEXICAL_SUPPORT and numbers_ok
    return {
        "entailment": ent,
        "contradiction": contra,
        "lexical": lexical,
        "numbers_ok": numbers_ok,
        "supported": ent >= 0.5 or by_lexical,
        "method": "nli" if ent >= 0.5 else "lexical" if by_lexical else None,
    }


def entailment(premises: list[str], hypothesis: str) -> tuple[float, float]:
    """Entailment and contradiction probability of the claim given its most relevant source sentences."""
    premise = focus_premise(premises, hypothesis)
    if not premise:
        return 0.0, 0.0
    probs = nli_probs([(premise, hypothesis)])
    return float(probs[0, 0]), float(probs[0, 2])


INTENT_LABELS = {
    "analytical": "counting, totals or statistics over many records",
    "overview": "an overview, summary or onboarding briefing about a product",
    "knowledge": "a specific engineering question about an issue, test, part, supplier or document",
    "chitchat": "a greeting or small talk",
}
_ANALYTICAL = re.compile(
    r"\b(how many|number of|count|total|average|mean|most|least|top \d+|per (year|plant|"
    r"component|supplier)|ranking|statistics)\b",
    re.I,
)
_CHITCHAT = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b[\s!.?]*$", re.I
)


def classify_intent(question: str) -> tuple[str, dict]:
    """Rules first (cheap, precise), zero-shot NLI for the rest."""
    if _CHITCHAT.match(question):
        return "chitchat", {"method": "rule"}
    if _ANALYTICAL.search(question):
        return "analytical", {"method": "rule"}
    res = _zero_shot()(
        question, candidate_labels=list(INTENT_LABELS.values()), hypothesis_template="This is {}."
    )
    by_desc = {v: k for k, v in INTENT_LABELS.items()}
    ranked = [
        (by_desc[lbl], round(float(sc), 3)) for lbl, sc in zip(res["labels"], res["scores"], strict=True)
    ]
    intent = ranked[0][0] if ranked[0][0] != "chitchat" else "knowledge"
    return intent, {"method": "zero-shot NLI", "scores": dict(ranked)}


@cache
def _zero_shot():
    from transformers import pipeline

    tok, model, _, _ = _nli()
    return pipeline("zero-shot-classification", model=model, tokenizer=tok, device=model.device)
