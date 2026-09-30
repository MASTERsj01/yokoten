"""Settings (from .env) and the runtime config that the UI/eval can switch."""

import json
import os
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(os.environ.get("YOKOTEN_ROOT", Path(__file__).resolve().parents[2]))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    groq_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    hf_home: str = ""
    data_dir: Path = ROOT / "data"
    var_dir: Path = ROOT / "var"
    cors_origins: str = "http://localhost:3000"
    demo_mode: bool = False  # read-only + rate limited (public deployment)
    rate_limit_per_min: int = 20
    max_upload_mb: int = 20
    ocr_engine: str = "auto"
    auto_ingest: bool = True  # generate + ingest the demo corpus on first start when the database is empty  # auto (tesseract if installed, else easyocr) | tesseract | easyocr

    @property
    def corpus_dir(self) -> Path:
        return self.data_dir / "corpus"

    @property
    def cache_dir(self) -> Path:
        """Large model caches (EasyOCR, ...) live next to HF_HOME when it is set (e.g. on D:)."""
        return Path(self.hf_home).parent if self.hf_home else self.var_dir / "cache"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.var_dir / 'yokoten.db').as_posix()}"


settings = Settings()
settings.var_dir.mkdir(parents=True, exist_ok=True)
# Must be set before transformers / sentence-transformers are imported (they are imported lazily).
if settings.hf_home:
    os.environ.setdefault("HF_HOME", settings.hf_home)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


class RuntimeConfig(BaseModel):
    """Everything the Settings page and the eval ablations can change."""

    llm_provider: Literal["groq", "gemini", "ollama", "local"] = "groq"
    llm_model: str = ""  # empty = provider default
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chunking: Literal["fixed", "recursive", "structure", "parent_child"] = "parent_child"
    vector_store: Literal["faiss", "chroma"] = "faiss"
    faiss_index: Literal["flat", "hnsw"] = "flat"
    retrieval_mode: Literal["dense", "bm25", "hybrid"] = "hybrid"
    reranker: bool = True
    top_k: int = 6
    candidates: int = 30
    query_rewrite: bool = True
    use_filters: bool = True
    prompt_version: str = "v2"
    abstain_threshold: float = 0.2  # min sigmoid(rerank score) of best chunk; calibrated on the dev split
    abstain_threshold_dense: float = 0.55  # used when the reranker is off (top cosine similarity)
    collections: list[str] = ["engineering"]
    sql_route: bool = True  # analytical questions -> text-to-SQL (feature K)
    use_verified: bool = True  # boost SME-verified answers (feature M)
    verified_similarity: float = 0.88


RUNTIME_FILE = settings.var_dir / "runtime.json"


def load_runtime() -> RuntimeConfig:
    if RUNTIME_FILE.exists():
        return RuntimeConfig.model_validate_json(RUNTIME_FILE.read_text("utf-8"))
    return RuntimeConfig()


def save_runtime(cfg: RuntimeConfig) -> None:
    RUNTIME_FILE.write_text(json.dumps(cfg.model_dump(), indent=2), "utf-8")


@cache
def device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"
