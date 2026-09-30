"""SME verification loop (feature M): verified / corrected answers are reused for near-identical questions."""

import numpy as np

from yokoten.config import RuntimeConfig
from yokoten.db import VerifiedAnswer, select, session
from yokoten.retrieval.embeddings import EmbeddingCache


def match(standalone: str, cfg: RuntimeConfig) -> dict | None:
    """Most similar verified question (cosine on the same embedding model); None below the threshold."""
    with session() as s:
        rows = list(s.exec(select(VerifiedAnswer).order_by(VerifiedAnswer.id.desc())).all())
    if not rows:
        return None
    cache = EmbeddingCache(cfg.embedding_model)
    vecs = cache.embed([r.standalone for r in rows] + [standalone])
    sims = vecs[:-1] @ vecs[-1]
    i = int(np.argmax(sims))
    if sims[i] < cfg.verified_similarity:
        return None
    r = rows[i]
    return {
        "id": r.id,
        "question": r.question,
        "answer": r.answer,
        "status": r.status,
        "note": r.note,
        "similarity": round(float(sims[i]), 3),
        "role": r.role,
    }
