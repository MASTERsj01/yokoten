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
NLI_MODEL = "cross-encoder/nli-deberta-v3-xsmall"


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


def windows(text: str, size: int = 900, overlap: int = 250) -> list[str]:
    if len(text) <= size:
        return [text]
    return [text[i : i + size] for i in range(0, len(text) - overlap, size - overlap)]


def entailment(premises: list[str], hypothesis: str) -> tuple[float, float]:
    """Best entailment probability of the hypothesis over all premise windows, and the contradiction prob there."""
    pairs = [(w, hypothesis) for p in premises for w in windows(p)]
    if not pairs:
        return 0.0, 0.0
    probs = nli_probs(pairs)
    best = int(np.argmax(probs[:, 0]))
    return float(probs[best, 0]), float(probs[best, 2])


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
