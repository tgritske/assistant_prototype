"""LLM backend abstraction + auto-detecting router.

The dispatcher's "AI" job (structured extraction, suggestions, translation)
is delegated to whichever backend is available. Priority order:

    1. Claude (Anthropic) — default, best quality, needs ANTHROPIC_API_KEY
    2. Ollama (local)     — fully offline fallback, needs `ollama` running on :11434
    3. None               — falls back to rule-based per-scenario fallback

Each backend implements a common async interface:
    async def extract(self, transcript: str) -> Optional[ClaudeExtraction]
    async def translate_phrases(self, target_language: str, phrases: list[str]) -> list[str]
    async def translate_text(self, target_language: str, text: str, source_language: str | None = None) -> str
    .name: human-readable label for the UI
    .model: the specific model id in use
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

import httpx

from schemas import ClaudeExtraction

log = logging.getLogger(__name__)


class LLMBackend(Protocol):
    name: str
    model: str

    async def extract(
        self, transcript: str, worker_context: str | None = None
    ) -> Optional[ClaudeExtraction]: ...
    async def translate_phrases(
        self, target_language: str, source_phrases: list[str]
    ) -> list[str]: ...
    async def translate_text(
        self, target_language: str, text: str, source_language: str | None = None
    ) -> str: ...


# ─── Auto-detection ──────────────────────────────────────────────────────


def _looks_like_real_key(value: Optional[str], prefix: str) -> bool:
    if not value:
        return False
    v = value.strip()
    if not v.startswith(prefix):
        return False
    # Reject obvious placeholders
    placeholders = {"...", "REPLACE", "your", "xxx", "stub", "fake", "test"}
    lower = v.lower()
    if any(p in lower for p in placeholders):
        return False
    return len(v) > len(prefix) + 10


def _ollama_reachable(host: str = "http://localhost:11434") -> bool:
    try:
        r = httpx.get(f"{host}/api/tags", timeout=0.5)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_has_model(model: str, host: str = "http://localhost:11434") -> bool:
    try:
        r = httpx.get(f"{host}/api/tags", timeout=0.5)
        if r.status_code != 200:
            return False
        names = {m.get("name", "") for m in r.json().get("models", [])}
        # Ollama reports names like "qwen2.5:7b-instruct" or "qwen2.5:latest"
        if model in names:
            return True
        base = model.split(":")[0]
        return any(n.split(":")[0] == base for n in names)
    except Exception:
        return False


# ─── Factory ─────────────────────────────────────────────────────────────


def build_backend() -> Optional[LLMBackend]:
    """Pick the best available backend at startup.

    Respects LLM_BACKEND env var for explicit override:
        LLM_BACKEND=claude|ollama|none|auto (default)
    """
    forced = (os.environ.get("LLM_BACKEND") or "auto").lower().strip()

    order: list[str]
    if forced == "auto":
        order = ["claude", "ollama"]
    elif forced == "none":
        return None
    else:
        order = [forced]

    for candidate in order:
        backend = _try_build(candidate)
        if backend is not None:
            log.info(
                "[llm] using %s (model=%s)", backend.name, backend.model
            )
            return backend

    log.warning(
        "[llm] no LLM backend available — falling back to rule-based extraction. "
        "Set ANTHROPIC_API_KEY, or run `ollama serve` with a model pulled."
    )
    return None


def _try_build(kind: str) -> Optional[LLMBackend]:
    # Lazy import so missing deps for one backend don't break others
    if kind == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not _looks_like_real_key(key, "sk-ant-"):
            return None
        try:
            from services.claude_service import ClaudeService

            return ClaudeService()
        except Exception as e:
            log.warning("[llm] claude init failed: %s", e)
            return None

    if kind == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if not _ollama_reachable(host):
            return None
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
        if not _ollama_has_model(model, host):
            log.warning(
                "[llm] ollama reachable at %s but model %r not pulled — run "
                "`ollama pull %s`",
                host,
                model,
                model,
            )
            return None
        try:
            from services.openai_compat import OpenAICompatBackend

            return OpenAICompatBackend(
                name="Ollama (local)",
                base_url=f"{host}/v1",
                api_key="ollama",  # ollama ignores this
                model=model,
                supports_prompt_cache=False,
            )
        except Exception as e:
            log.warning("[llm] ollama init failed: %s", e)
            return None

    log.warning("[llm] unknown backend: %s", kind)
    return None
