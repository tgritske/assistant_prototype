from __future__ import annotations

import logging
import os
from typing import Optional

from anthropic import AsyncAnthropic

from prompts import SYSTEM_PROMPT, EXTRACTION_TOOL
from schemas import ClaudeExtraction, FormFields, Suggestion
from services.form_normalizer import normalize_detected_language, normalize_form_dict

log = logging.getLogger(__name__)

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
# Translation runs on every new caller turn; Haiku is fast enough and cheap.
TRANSLATE_MODEL = os.environ.get(
    "CLAUDE_TRANSLATE_MODEL", "claude-haiku-4-5-20251001"
)

TRANSLATE_TEXT_SYSTEM = (
    "You translate live emergency-dispatch audio transcripts to the requested "
    "target language. Return ONLY the translation, no commentary, no quotes, "
    "no leading/trailing whitespace beyond the translation itself. Use natural "
    "phrasing for a live emergency call. Preserve all addresses, names, "
    "numbers, units of measure, and the urgency conveyed in the source. "
    "If the source already matches the target language, return it unchanged."
)

TRANSLATE_PHRASES_SYSTEM = (
    "You translate dispatcher phrases to the requested target language for an "
    "emergency call where the caller does not speak English. Use natural, "
    "clear wording the caller will understand immediately. Preserve urgency, "
    "names, numbers, and addresses. Return one translation per input line, in "
    "the same order, with no numbering, prefixes, or extra commentary."
)


class ClaudeService:
    """Streaming wrapper around the Anthropic SDK that extracts structured
    incident data from a growing call transcript.

    Uses tool_use for reliable JSON output and prompt caching on the system
    prompt so repeated calls during a single call stay cheap and fast.
    """

    name = "Claude"

    def __init__(self, api_key: Optional[str] = None, model: str = MODEL):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Create backend/.env with your key."
            )
        self.client = AsyncAnthropic(api_key=key)
        self.model = model

    async def extract(self, transcript: str) -> Optional[ClaudeExtraction]:
        """Send full transcript to Claude and return parsed structured output."""
        if not transcript.strip():
            return None

        user_message = (
            "Current call transcript (in progress):\n"
            f'"""\n{transcript}\n"""\n\n'
            "Extract structured incident data. Use the tool."
        )

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "extract_incident_data"},
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as e:
            log.error("Claude extraction failed: %s", e)
            return None

        tool_use = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use"),
            None,
        )
        if tool_use is None:
            log.warning("Claude returned no tool_use block")
            return None

        data = tool_use.input
        try:
            form = FormFields(**normalize_form_dict(
                data.get("form_fields") or {},
                source_text=transcript,
                operator_text=transcript,
            ))
            suggestions = [Suggestion(**s) for s in (data.get("suggestions") or [])]
            return ClaudeExtraction(
                form_fields=form,
                suggestions=suggestions,
                highlight_keywords=data.get("highlight_keywords") or [],
                priority_reasoning=data.get("priority_reasoning"),
                detected_language=normalize_detected_language(data.get("detected_language")),
            )
        except Exception as e:
            log.error("Failed to parse Claude tool output: %s — data=%r", e, data)
            return None

    async def translate_phrases(
        self, target_language: str, source_phrases: list[str]
    ) -> list[str]:
        """Translate a list of common dispatcher phrases into the caller's language.

        Used when the caller is non-English-speaking — the dispatcher can then
        click a phrase to play it aloud in the caller's language via TTS.
        """
        if not source_phrases:
            return []

        user_message = (
            f"Target language: {target_language}\n"
            "Phrases (one per line):\n"
            + "\n".join(source_phrases)
        )

        try:
            response = await self.client.messages.create(
                model=TRANSLATE_MODEL,
                max_tokens=800,
                system=[
                    {
                        "type": "text",
                        "text": TRANSLATE_PHRASES_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            text = response.content[0].text.strip()
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            return lines[: len(source_phrases)]
        except Exception as e:
            log.error("Phrase translation failed: %s", e)
            return source_phrases  # fallback to English

    async def translate_text(
        self,
        target_language: str,
        text: str,
        source_language: str | None = None,
    ) -> str:
        if not text.strip():
            return text

        source_hint = (
            f"Source language: {source_language}\n" if source_language else ""
        )
        user_message = (
            f"{source_hint}"
            f"Target language: {target_language}\n"
            "Source text:\n"
            f"{text}"
        )
        try:
            response = await self.client.messages.create(
                model=TRANSLATE_MODEL,
                max_tokens=1000,
                system=[
                    {
                        "type": "text",
                        "text": TRANSLATE_TEXT_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            translated = response.content[0].text.strip()
            return translated or text
        except Exception as e:
            log.error("Text translation failed: %s", e)
            return text
