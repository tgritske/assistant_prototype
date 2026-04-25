from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, runtime_checkable

import numpy as np

from .whisper_service import Segment

log = logging.getLogger(__name__)


@runtime_checkable
class Transcriber(Protocol):
    name: str
    model_name: str

    async def warmup(self) -> None: ...

    async def transcribe_array(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        use_vad: bool = True,
    ) -> tuple[list[Segment], Optional[str]]: ...

    async def transcribe_file(
        self, file_path: str, language: Optional[str] = None
    ) -> tuple[list[Segment], Optional[str]]: ...


_singleton: Optional[Transcriber] = None


def get_transcriber() -> Transcriber:
    global _singleton
    if _singleton is not None:
        return _singleton

    provider = os.environ.get("STT_PROVIDER", "whisper").strip().lower()

    if provider == "reson8":
        from .reson8_service import get_reson8_service
        _singleton = get_reson8_service()
    elif provider == "whisper":
        from .whisper_service import get_whisper_service
        _singleton = get_whisper_service()
    else:
        log.warning(
            "Unknown STT_PROVIDER=%r; falling back to whisper", provider
        )
        from .whisper_service import get_whisper_service
        _singleton = get_whisper_service()

    log.info("Transcriber: %s (model=%s)", _singleton.name, _singleton.model_name)
    return _singleton
