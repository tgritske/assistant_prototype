from __future__ import annotations

import asyncio
import logging
from typing import Optional

import edge_tts

log = logging.getLogger(__name__)


# A curated set of natural-sounding neural voices covering the most common
# non-English caller languages a US dispatcher is likely to encounter.
DEFAULT_VOICES: dict[str, str] = {
    "en": "en-US-AriaNeural",
    "en-US": "en-US-AriaNeural",
    "es": "es-US-PalomaNeural",
    "es-US": "es-US-PalomaNeural",
    "es-ES": "es-ES-ElviraNeural",
    "es-MX": "es-MX-DaliaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
    "uk": "uk-UA-PolinaNeural",
    "uk-UA": "uk-UA-PolinaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "pt-BR": "pt-BR-FranciscaNeural",
    "pl": "pl-PL-ZofiaNeural",
    "hi": "hi-IN-SwaraNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "tl": "fil-PH-BlessicaNeural",
    "it": "it-IT-ElsaNeural",
}


COMMON_DISPATCHER_PHRASES: list[str] = [
    "911, what is your emergency?",
    "Stay on the line, help is on the way.",
    "What is your address?",
    "Is anyone hurt?",
    "Is the person breathing?",
    "Are you in a safe place?",
    "Do you see any weapons?",
    "Can you get to a safe place?",
    "How many people are there?",
    "What is the patient's age?",
]


class TTSService:
    """Async text-to-speech via Microsoft Edge voices.

    Returns MP3 bytes suitable for playback in <audio> on the client.
    """

    def __init__(self):
        self._voice_cache: dict[str, str] = {}

    def voice_for(self, language: str) -> str:
        """Resolve a BCP-47 tag to an Edge voice, falling back progressively."""
        if language in DEFAULT_VOICES:
            return DEFAULT_VOICES[language]
        base = language.split("-")[0].lower()
        if base in DEFAULT_VOICES:
            return DEFAULT_VOICES[base]
        return DEFAULT_VOICES["en-US"]

    async def synthesize(self, text: str, language: str = "en-US") -> bytes:
        """Return MP3 bytes for the given text in the given language."""
        voice = self.voice_for(language)
        communicate = edge_tts.Communicate(text=text, voice=voice)
        chunks: list[bytes] = []
        async for event in communicate.stream():
            if event["type"] == "audio":
                chunks.append(event["data"])
        return b"".join(chunks)

    async def synthesize_to_file(
        self, text: str, language: str, path: str
    ) -> None:
        data = await self.synthesize(text, language)
        with open(path, "wb") as f:
            f.write(data)


_singleton: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    global _singleton
    if _singleton is None:
        _singleton = TTSService()
    return _singleton
