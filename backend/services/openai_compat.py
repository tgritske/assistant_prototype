"""OpenAI-compatible LLM backend.

Works for any service that exposes an OpenAI-shaped `/v1/chat/completions`
endpoint with function-calling support. Tested against:
    - Ollama (http://localhost:11434/v1)

Uses OpenAI-style tool_use, which maps trivially from the Claude schema in
`prompts.py` (just re-wrap as `{"type": "function", "function": {...}}`).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from prompts import SYSTEM_PROMPT, EXTRACTION_TOOL
from schemas import ClaudeExtraction, FormFields, Suggestion
from services.form_normalizer import normalize_detected_language, normalize_form_dict

log = logging.getLogger(__name__)


# Convert the Claude tool schema to OpenAI function-calling shape once.
_OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": EXTRACTION_TOOL["name"],
        "description": EXTRACTION_TOOL["description"],
        "parameters": EXTRACTION_TOOL["input_schema"],
    },
}


class OpenAICompatBackend:
    """LLM backend for any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        supports_prompt_cache: bool = False,
        extra_headers: Optional[dict] = None,
    ):
        self.name = name
        self.model = model
        self._supports_prompt_cache = supports_prompt_cache
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers=extra_headers or {},
        )

    async def extract(self, transcript: str) -> Optional[ClaudeExtraction]:
        if not transcript.strip():
            return None

        user_message = (
            "Current call transcript (in progress):\n"
            f'"""\n{transcript}\n"""\n\n'
            "Extract structured incident data. Use the extract_incident_data tool."
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                tools=[_OPENAI_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": EXTRACTION_TOOL["name"]},
                },
            )
        except Exception as e:
            log.error("[%s] extract call failed: %s", self.name, e)
            return None

        try:
            choice = response.choices[0]
            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                content = getattr(choice.message, "content", None) or ""
                log.warning(
                    "[%s] model returned no tool call (finish=%s) — content=%r",
                    self.name,
                    choice.finish_reason,
                    content[:300],
                )
                return None
            raw_args = tool_calls[0].function.arguments
            data = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except Exception as e:
            log.error("[%s] failed to parse tool call: %s", self.name, e)
            return None

        try:
            raw_form = _extract_form_fields(data, self.name)
            form = FormFields(**normalize_form_dict(
                _prune_nulls(raw_form or {}),
                source_text=transcript,
                operator_text=transcript,
            ))

            # Build suggestions individually — skip malformed ones rather than
            # failing the whole extraction. Models sometimes return null triggers.
            suggestions: list[Suggestion] = []
            for s in _normalize_suggestions(data.get("suggestions") or []):
                if not isinstance(s, dict):
                    continue
                if s.get("trigger") is None:
                    s = {**s, "trigger": ""}
                try:
                    suggestions.append(Suggestion(**s))
                except Exception as sug_err:
                    log.debug("[%s] skipping malformed suggestion %r: %s",
                              self.name, s.get("id"), sug_err)

            highlight_keywords = data.get("highlight_keywords") or []
            if not isinstance(highlight_keywords, list):
                highlight_keywords = [str(highlight_keywords)]

            return ClaudeExtraction(
                form_fields=form,
                suggestions=suggestions,
                highlight_keywords=[str(x) for x in highlight_keywords if str(x).strip()],
                priority_reasoning=data.get("priority_reasoning"),
                detected_language=normalize_detected_language(data.get("detected_language")),
            )
        except Exception as e:
            log.error(
                "[%s] failed to build ClaudeExtraction: %s — keys=%s",
                self.name,
                e,
                list(data.keys()) if isinstance(data, dict) else type(data),
            )
            return ClaudeExtraction()

    async def translate_phrases(
        self, target_language: str, source_phrases: list[str]
    ) -> list[str]:
        if not source_phrases:
            return []
        prompt = (
            f"Translate these emergency-dispatch phrases to {target_language}. "
            "Use natural, clear wording a caller will understand immediately. "
            "Preserve urgency, names, numbers, and addresses. "
            "Return them one per line in the same order, nothing else.\n\n"
            + "\n".join(source_phrases)
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=800,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            text = (response.choices[0].message.content or "").strip()
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            # Some models prefix with numbers or quotes — strip lightly
            cleaned = [_strip_prefix(ln) for ln in lines]
            return cleaned[: len(source_phrases)] or source_phrases
        except Exception as e:
            log.error("[%s] translate failed: %s", self.name, e)
            return source_phrases

    async def translate_text(
        self,
        target_language: str,
        text: str,
        source_language: str | None = None,
    ) -> str:
        if not text.strip():
            return text
        source_hint = f" from {source_language}" if source_language else ""
        prompt = (
            f"Translate the following emergency-dispatch text{source_hint} to {target_language}. "
            "Return only the translation. Use natural phrasing for a live emergency call. "
            "Preserve addresses, names, numbers, and emergency meaning.\n\n"
            f"{text}"
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=900,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            )
            translated = (response.choices[0].message.content or "").strip()
            return translated or text
        except Exception as e:
            log.error("[%s] translate_text failed: %s", self.name, e)
            return text


def _prune_nulls(d: dict) -> dict:
    """Drop explicit nulls so Pydantic doesn't choke on e.g. num_victims=None
    typed as int. Pydantic's Optional[int] accepts None, but some smaller
    models emit the string "null" for numeric fields — scrub those too."""
    out: dict = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, str) and v.strip().lower() in {"null", "none", "n/a", ""}:
            continue
        out[k] = v
    return out


def _extract_form_fields(data: dict, backend_name: str) -> dict:
    candidates: list[object] = []
    if isinstance(data, dict):
        candidates.append(data.get("form_fields"))
        candidates.append(data.get("object"))
        for key, val in data.items():
            if key in {"suggestions", "highlight_keywords", "priority_reasoning", "detected_language"}:
                continue
            candidates.append(val)

    for candidate in candidates:
        normalized = _normalize_mapping(candidate)
        if normalized and any(
            key in normalized for key in ("incident_type", "location", "priority", "description")
        ):
            return normalized

    log.debug("[%s] could not find normalized form fields in payload keys=%s", backend_name, list(data.keys()))
    return {}


def _normalize_mapping(value: object) -> dict:
    if isinstance(value, dict):
        # Sometimes "object" wraps the actual object under an extra key.
        if set(value.keys()) == {"properties"} and isinstance(value.get("properties"), dict):
            return _normalize_mapping(value["properties"])
        return dict(value)

    if isinstance(value, list):
        out: dict = {}
        for item in value:
            if isinstance(item, dict):
                if "key" in item and "value" in item:
                    out[str(item["key"])] = item["value"]
                    continue
                if len(item) == 1:
                    k, v = next(iter(item.items()))
                    out[str(k)] = v
                    continue
                if "name" in item and "arguments" in item:
                    out[str(item["name"])] = item["arguments"]
                    continue
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                out[str(item[0])] = item[1]
        return out

    return {}


def _normalize_suggestions(value: object) -> list[dict]:
    if isinstance(value, list):
        out: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str):
                out.append(
                    {
                        "id": _slug(item)[:40] or "suggestion",
                        "trigger": "",
                        "question": item,
                        "urgency": "medium",
                        "category": "info",
                        "suggestion_type": "ask",
                    }
                )
        return out
    if isinstance(value, str) and value.strip():
        return [
            {
                "id": _slug(value)[:40] or "suggestion",
                "trigger": "",
                "question": value.strip(),
                "urgency": "medium",
                "category": "info",
                "suggestion_type": "ask",
            }
        ]
    return []


def _strip_prefix(line: str) -> str:
    # "1. Hello" / "1) Hello" / '"Hello"' → "Hello"
    s = line.strip()
    if s.startswith(('"', "'")) and s.endswith(('"', "'")):
        s = s[1:-1].strip()
    for i, ch in enumerate(s):
        if ch.isdigit() or ch in ".)-: ":
            continue
        s = s[i:]
        break
    return s.strip()


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")
