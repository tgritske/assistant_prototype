from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
# Model tradeoffs (M3 CPU, int8):
#   "tiny"   (~75MB)   ~0.05s per 1s chunk — fast but poor on Russian/accented speech
#   "base"  (~145MB)   ~0.12s per 1s chunk — decent English, struggles with Russian
#   "small"  (~460MB)  ~0.35s per 1s chunk — good multilingual quality, default
#   "medium" (~1.5GB)  ~1.2s per 1s chunk — too slow for live streaming
# For the no-overlap 1s-chunk approach the total latency is chunk_time+inference_time.
# small: 1.0s + 0.35s = ~1.35s — acceptable and much better quality than base.
# Override with WHISPER_MODEL=tiny|base|medium.
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))

SAMPLE_RATE = 16000


@dataclass
class Segment:
    text: str
    start: float
    end: float
    is_final: bool = True


@dataclass
class TranscriptionState:
    """Per-call transcription state. The server buffers incoming PCM samples
    and runs inference in windows. On each window we produce provisional text
    (final=False) which is later replaced once enough context has accumulated.
    """

    pcm: list[np.ndarray] = field(default_factory=list)
    duration_sec: float = 0.0
    language: Optional[str] = None
    final_segments: list[Segment] = field(default_factory=list)
    provisional_text: str = ""

    def full_text(self) -> str:
        finals = " ".join(s.text.strip() for s in self.final_segments)
        if self.provisional_text:
            return (finals + " " + self.provisional_text).strip()
        return finals.strip()


class WhisperService:
    """CPU/Metal-backed streaming-ish transcription via faster-whisper.

    faster-whisper isn't a true streaming ASR — it processes whole audio
    arrays. For live-ish behavior we re-transcribe a sliding window every
    ~1.5 seconds. Older audio becomes "final" and is locked in; newer audio
    stays "provisional" until it ages out of the window.
    """

    name = "whisper"

    def __init__(self):
        log.info("Loading Whisper model size=%s compute=%s device=%s",
                 MODEL_SIZE, COMPUTE_TYPE, DEVICE)
        self.model_name = MODEL_SIZE
        self.model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            download_root=os.path.join(os.path.dirname(__file__), "..", "models"),
        )
        self._lock = asyncio.Lock()
        self._warmed = False

    async def warmup(self):
        if self._warmed:
            return
        silence = np.zeros(SAMPLE_RATE, dtype=np.float32)  # 1s of silence
        await asyncio.to_thread(self._transcribe_sync, silence, None)
        self._warmed = True
        log.info("Whisper warm-up complete")

    def _transcribe_sync(
        self,
        audio: np.ndarray,
        language: Optional[str],
        initial_prompt: Optional[str] = None,
        use_vad: bool = True,
    ):
        kwargs: dict = dict(
            language=language,
            beam_size=BEAM_SIZE,
            condition_on_previous_text=False,
            word_timestamps=False,
        )
        if use_vad:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = {"min_silence_duration_ms": 300}
        else:
            # VAD aggressively trims short live-mic chunks; skip it when the
            # caller already gates silence on the frontend side.
            kwargs["vad_filter"] = False
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        segments, info = self.model.transcribe(audio, **kwargs)
        return list(segments), info

    async def transcribe_array(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        use_vad: bool = True,
    ) -> tuple[list[Segment], Optional[str]]:
        async with self._lock:
            segments, info = await asyncio.to_thread(
                self._transcribe_sync, audio, language, initial_prompt, use_vad
            )
        out = [
            Segment(text=s.text.strip(), start=s.start, end=s.end, is_final=True)
            for s in segments
            if s.text.strip()
        ]
        return out, info.language

    async def transcribe_file(
        self, file_path: str, language: Optional[str] = None
    ) -> tuple[list[Segment], Optional[str]]:
        async with self._lock:
            segments, info = await asyncio.to_thread(
                self._transcribe_file_sync, file_path, language
            )
        out = [
            Segment(text=s.text.strip(), start=s.start, end=s.end, is_final=True)
            for s in segments
            if s.text.strip()
        ]
        return out, info.language

    def _transcribe_file_sync(self, file_path: str, language: Optional[str]):
        segments, info = self.model.transcribe(
            file_path,
            language=language,
            beam_size=BEAM_SIZE,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False,
        )
        return list(segments), info


_service_singleton: Optional[WhisperService] = None


def get_whisper_service() -> WhisperService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = WhisperService()
    return _service_singleton
