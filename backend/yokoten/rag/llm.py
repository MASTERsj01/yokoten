"""LLM providers behind LangChain chat models + a disk cache for every call (answers, rewrites, judge, SQL).

groq / gemini   hosted free tiers (keys in .env)
ollama          local server - "confidential data never leaves the plant"
local           Hugging Face Transformers model in-process (CPU works; no key, no server) - last-resort fallback
"""

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cache

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from yokoten.config import device, settings
from yokoten.db import LlmCache, session

PROVIDERS = {
    "groq": {
        "default": "llama-3.3-70b-versatile",
        "prefer": [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "llama-3.1-8b-instant",
        ],
        "min_interval_s": 2.1,
    },
    "gemini": {
        "default": "gemini-2.5-flash",
        "prefer": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
        "min_interval_s": 6.5,
    },
    "ollama": {
        "default": "qwen3:8b",
        "prefer": ["qwen3:8b", "llama3.1:8b", "llama3.2:3b"],
        "min_interval_s": 0,
    },
    "local": {
        "default": "Qwen/Qwen2.5-1.5B-Instruct",
        "prefer": ["Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-0.5B-Instruct"],
        "min_interval_s": 0,
    },
}
ORDER = ["groq", "gemini", "ollama", "local"]


# ------------------------------------------------------------------ availability + model listing
@cache
def _ollama_up(base_url: str) -> bool:
    try:
        return httpx.get(f"{base_url}/api/tags", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


def available() -> dict[str, bool]:
    return {
        "groq": bool(settings.groq_api_key),
        "gemini": bool(settings.google_api_key),
        "ollama": _ollama_up(settings.ollama_base_url),
        "local": True,
    }


_models_cache: dict[str, tuple[float, list[str]]] = {}


def list_models(provider: str) -> list[str]:
    hit = _models_cache.get(provider)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    models: list[str] = []
    try:
        if provider == "groq" and settings.groq_api_key:
            r = httpx.get(
                "https://api.groq.com/openai/v1/models",
                timeout=10,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            )
            models = sorted(m["id"] for m in r.json().get("data", []) if m.get("active", True))
        elif provider == "gemini" and settings.google_api_key:
            r = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                timeout=10,
                params={"key": settings.google_api_key, "pageSize": 200},
            )
            models = sorted(
                m["name"].removeprefix("models/")
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            )
        elif provider == "ollama" and _ollama_up(settings.ollama_base_url):
            models = sorted(
                m["name"]
                for m in httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3).json()["models"]
            )
        elif provider == "local":
            models = list(PROVIDERS["local"]["prefer"])
    except (httpx.HTTPError, ValueError, KeyError):
        models = []
    _models_cache[provider] = (time.time(), models)
    return models


def resolve(provider: str | None, model: str | None) -> tuple[str, str]:
    """Pick a usable provider/model: the requested one if available, else the first available in ORDER."""
    avail = available()
    if not provider or not avail.get(provider):
        provider = next(p for p in ORDER if avail[p])
    if not model:
        listed = list_models(provider) if provider != "local" else []
        model = next(
            (m for m in PROVIDERS[provider]["prefer"] if m in listed), PROVIDERS[provider]["default"]
        )
    return provider, model


# ------------------------------------------------------------------ chat models
@cache
def chat_model(provider: str, model: str, max_tokens: int = 700) -> BaseChatModel:
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model_name=model,
            groq_api_key=settings.groq_api_key,
            temperature=0,
            max_retries=4,
            max_tokens=max_tokens,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        extra = {"thinking_budget": 0} if "2.5-flash" in model else {}
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=0,
            max_retries=4,
            max_output_tokens=max_tokens,
            **extra,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            base_url=settings.ollama_base_url,
            temperature=0,
            reasoning=False,
            num_ctx=8192,
            num_predict=max_tokens,
        )
    if provider == "local":
        import torch
        from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline

        pipe = HuggingFacePipeline.from_model_id(
            model_id=model,
            task="text-generation",
            device=0 if device() == "cuda" else -1,
            model_kwargs={"dtype": torch.bfloat16 if device() == "cpu" else torch.float16},
            pipeline_kwargs={
                "max_new_tokens": min(max_tokens, 450),
                "do_sample": False,
                "return_full_text": False,
            },
        )
        return ChatHuggingFace(llm=pipe)
    raise ValueError(f"unknown provider {provider}")


# ------------------------------------------------------------------ calls (streamed, cached, throttled)
_last_call: dict[str, float] = {}
_lock = threading.Lock()


def _throttle(provider: str) -> None:
    gap = PROVIDERS[provider]["min_interval_s"]
    with _lock:
        wait = _last_call.get(provider, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[provider] = time.time()


def _text(chunk) -> str:
    t = getattr(chunk, "text", None)  # langchain-core 1.x: str-like accessor over text content blocks
    return str(t) if isinstance(t, str) else str(chunk.content)


@dataclass
class LlmCall:
    provider: str
    model: str
    text: str = ""
    cached: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    ms: float = 0.0
    first_token_ms: float | None = None
    meta: dict = field(default_factory=dict)


def _key(provider: str, model: str, messages: list[BaseMessage]) -> str:
    payload = json.dumps([provider, model, [(m.type, m.content) for m in messages]], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stream(
    messages: list[BaseMessage],
    provider: str,
    model: str,
    call: LlmCall | None = None,
    use_cache: bool = True,
    max_tokens: int = 700,
) -> Iterator[str]:
    """Yield text deltas. Fills `call` with usage/timing. Cached responses are replayed in small pieces."""
    call = call or LlmCall(provider, model)
    t0 = time.perf_counter()
    key = _key(provider, model, messages)
    if use_cache:
        with session() as s:
            hit = s.get(LlmCache, key)
        if hit:
            call.cached, call.text = True, hit.response
            call.input_tokens, call.output_tokens = hit.usage.get("input", 0), hit.usage.get("output", 0)
            call.first_token_ms = (time.perf_counter() - t0) * 1000
            for i in range(0, len(hit.response), 24):
                yield hit.response[i : i + 24]
            call.ms = (time.perf_counter() - t0) * 1000
            return
    _throttle(provider)
    full = None
    parts: list[str] = []
    for chunk in chat_model(provider, model, max_tokens).stream(messages):
        full = chunk if full is None else full + chunk
        t = _text(chunk)
        if t:
            if call.first_token_ms is None:
                call.first_token_ms = (time.perf_counter() - t0) * 1000
            parts.append(t)
            yield t
    call.text = "".join(parts)
    usage = getattr(full, "usage_metadata", None) or {}
    prompt_chars = sum(len(str(m.content)) for m in messages)
    call.input_tokens = usage.get("input_tokens") or prompt_chars // 4
    call.output_tokens = usage.get("output_tokens") or len(call.text) // 4
    call.meta["usage_estimated"] = not usage
    call.ms = (time.perf_counter() - t0) * 1000
    with session() as s:
        s.merge(
            LlmCache(
                key=key,
                provider=provider,
                model=model,
                response=call.text,
                usage={"input": call.input_tokens, "output": call.output_tokens},
            )
        )
        s.commit()


def invoke(
    messages: list[BaseMessage], provider: str, model: str, use_cache: bool = True, max_tokens: int = 700
) -> LlmCall:
    call = LlmCall(provider, model)
    for _ in stream(messages, provider, model, call, use_cache, max_tokens):
        pass
    return call
