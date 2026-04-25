from __future__ import annotations

"""Reson8 cloud streaming STT adapter.

Conforms to the same `transcribe_array` / `transcribe_file` API as
WhisperService so it can be swapped via the STT_PROVIDER env var.

Integration style is per-chunk WebSocket: each call to transcribe_array
opens a fresh ws to wss://api.reson8.dev/v1/speech-to-text/realtime,
streams the chunk as raw pcm_s16le binary frames, sends a flush_request,
collects transcripts until flush_confirmation, and closes.

Trade-off: this defeats Reson8's persistent-stream latency advantage
(reconnect cost per chunk), but keeps the call-site contract identical
to faster-whisper for clean A/B comparison via env toggle.

Ignored params (no public Reson8 equivalent):
- initial_prompt: Whisper-style context biasing.
- use_vad: Reson8 handles VAD server-side.
"""

import asyncio
import json
import logging
import os
import ssl
import uuid
from typing import Optional

import certifi
import numpy as np
import websockets
from websockets.asyncio.client import connect as ws_connect

from .whisper_service import SAMPLE_RATE, Segment

log = logging.getLogger(__name__)


DEFAULT_ENDPOINT = "wss://api.reson8.dev/v1/speech-to-text/realtime"
SEND_CHUNK_BYTES = 3200  # ~100 ms of pcm_s16le @ 16 kHz mono


class Reson8Service:
    name = "reson8"

    def __init__(self):
        self.api_key = os.environ.get("RESON8_API_KEY", "").strip()
        self.endpoint = os.environ.get("RESON8_ENDPOINT", DEFAULT_ENDPOINT).strip()
        self.sample_rate = int(os.environ.get("RESON8_SAMPLE_RATE", str(SAMPLE_RATE)))
        self.model_name = os.environ.get("RESON8_MODEL", "default")
        # Python on macOS (python.org build) doesn't trust the system keychain,
        # so we must point TLS at certifi's bundle explicitly. Otherwise the
        # wss:// handshake fails with CERTIFICATE_VERIFY_FAILED.
        self._ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        if not self.api_key:
            log.warning("RESON8_API_KEY is empty; Reson8 calls will fail with 401")

    async def warmup(self) -> None:
        # Avoid a billable warmup; just surface obvious config issues at startup.
        if not self.api_key:
            log.warning("Reson8 warmup: RESON8_API_KEY not set")
        else:
            log.info("Reson8 warmup: endpoint=%s", self.endpoint)

    async def transcribe_array(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,  # noqa: ARG002 — interface compat
        use_vad: bool = True,  # noqa: ARG002 — interface compat
    ) -> tuple[list[Segment], Optional[str]]:
        if audio.size == 0:
            return [], language

        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()

        url = (
            f"{self.endpoint}"
            f"?encoding=pcm_s16le"
            f"&sample_rate={self.sample_rate}"
            f"&channels=1"
            f"&include_interim=false"
            f"&include_timestamps=true"
        )
        headers = {"Authorization": f"ApiKey {self.api_key}"}
        flush_id = uuid.uuid4().hex
        segments: list[Segment] = []

        try:
            async with ws_connect(url, additional_headers=headers, ssl=self._ssl_ctx) as ws:
                # Stream PCM in ~100 ms slices so the server can pipeline.
                for i in range(0, len(pcm), SEND_CHUNK_BYTES):
                    await ws.send(pcm[i : i + SEND_CHUNK_BYTES])

                await ws.send(json.dumps({"type": "flush_request", "id": flush_id}))

                async for raw in ws:
                    if isinstance(raw, (bytes, bytearray)):
                        continue
                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        log.debug("Reson8: non-json frame: %r", raw[:120])
                        continue

                    mtype = msg.get("type")
                    if mtype == "transcript":
                        text = (msg.get("text") or "").strip()
                        if not text:
                            continue
                        start = float(msg.get("start_ms", 0)) / 1000.0
                        dur = float(msg.get("duration_ms", 0)) / 1000.0
                        segments.append(
                            Segment(
                                text=text,
                                start=start,
                                end=start + dur,
                                is_final=True,
                            )
                        )
                    elif mtype == "flush_confirmation" and msg.get("id") == flush_id:
                        break
                    elif mtype == "error":
                        log.warning("Reson8 error frame: %s", msg)
        except websockets.exceptions.InvalidStatus as e:
            log.error("Reson8 WS rejected (auth/endpoint?): %s", e)
            raise
        except Exception:
            log.exception("Reson8 WS failed")
            raise

        # Reson8 doesn't echo a detected language; pass through caller's hint.
        return segments, language

    async def transcribe_file(
        self, file_path: str, language: Optional[str] = None
    ) -> tuple[list[Segment], Optional[str]]:
        # Decode to 16 kHz mono float32 via PyAV (already a faster-whisper dep)
        # then route through transcribe_array. Keeps one network code path.
        audio = await asyncio.to_thread(_decode_to_float32_mono, file_path, self.sample_rate)
        return await self.transcribe_array(audio, language=language)


def _decode_to_float32_mono(file_path: str, sample_rate: int) -> np.ndarray:
    import av

    container = av.open(file_path)
    try:
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                arr = resampled.to_ndarray()
                if arr.ndim > 1:
                    arr = arr.reshape(-1)
                chunks.append(arr.astype(np.int16))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        pcm16 = np.concatenate(chunks)
        return pcm16.astype(np.float32) / 32768.0
    finally:
        container.close()


_singleton: Optional[Reson8Service] = None


def get_reson8_service() -> Reson8Service:
    global _singleton
    if _singleton is None:
        _singleton = Reson8Service()
    return _singleton
