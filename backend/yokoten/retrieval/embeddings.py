"""Sentence Transformers embeddings with a per-model disk cache (keyed by text hash)."""

import hashlib
import json
from functools import cache

import numpy as np

from yokoten.config import device, settings

EMBED_MODELS = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "sentence-transformers/all-MiniLM-L6-v2": "",
    "BAAI/bge-base-en-v1.5": "Represent this sentence for searching relevant passages: ",
}


@cache
def model(name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device=device())


def slug(name: str) -> str:
    return name.split("/")[-1].replace(".", "_")


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    def __init__(self, name: str):
        self.name = name
        self.path = settings.var_dir / "emb" / f"{slug(name)}.npz"
        self.vecs: dict[str, np.ndarray] = {}
        if self.path.exists():
            z = np.load(self.path)
            self.vecs = dict(zip(json.loads(str(z["keys"])), z["vecs"], strict=True))

    def embed(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        keys = [_key(t) for t in texts]
        missing = sorted({k: t for k, t in zip(keys, texts, strict=True) if k not in self.vecs}.items())
        if missing:
            vecs = model(self.name).encode_document(
                [t for _, t in missing],
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            self.vecs.update({k: v.astype(np.float32) for (k, _), v in zip(missing, vecs, strict=True)})
            self.save()
        dim = model_dim(self.name) if not self.vecs else len(next(iter(self.vecs.values())))
        return np.stack([self.vecs[k] for k in keys]) if keys else np.zeros((0, dim), np.float32)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.vecs)
        np.savez(self.path, keys=json.dumps(keys), vecs=np.stack([self.vecs[k] for k in keys]))


def model_dim(name: str) -> int:
    return model(name).get_sentence_embedding_dimension()


def embed_query(name: str, text: str) -> np.ndarray:
    v = model(name).encode_query(
        [text], prompt=EMBED_MODELS.get(name) or None, normalize_embeddings=True, convert_to_numpy=True
    )
    return v[0].astype(np.float32)
