"""Verification: caller / worker channels stay separated end-to-end.

Drives CallSession through:
- two parallel routed audio chunks (caller + worker), checks each lands in the
  right queue and produces speaker-labeled dialogue turns
- live_transcript with speaker="worker", checks worker turn appended without
  contaminating caller transcript / final_segments
- _reset_call_state, checks both channel queues + dialogue_turns wiped

Run:
    cd backend
    python tests/test_dual_channel.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Disable LLM + force whisper so we don't hit external services.
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("OLLAMA_HOST", "")
os.environ.setdefault("STT_PROVIDER", "whisper")
os.environ.setdefault("WHISPER_MODEL_SIZE", "base")

import numpy as np

from main import CallSession, _handle_text
import json

from services.whisper_service import SAMPLE_RATE


class FakeWebSocket:
    class _State:
        name = "CONNECTED"

    def __init__(self):
        self.client_state = self._State()
        self.sent: list[dict] = []
        self.sent_bytes: list[bytes] = []

    async def send_json(self, payload):
        self.sent.append(payload)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def accept(self):
        pass

    async def close(self):
        self.client_state = type("S", (), {"name": "DISCONNECTED"})()


def _silence(seconds: float = 0.5) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


async def test_route_audio_chunk_separates_channels():
    ws = FakeWebSocket()
    s = CallSession(ws, call_id="dual-route")
    s.started = True

    # Route one chunk to each channel; we only care about queue placement here,
    # not transcription output (silence will produce no segments).
    s.route_audio_chunk("caller", _silence(0.5))
    s.route_audio_chunk("worker", _silence(0.5))

    caller_q = s.audio_channels["caller"].queue
    worker_q = s.audio_channels["worker"].queue
    assert caller_q.qsize() == 1, f"expected 1 caller chunk, got {caller_q.qsize()}"
    assert worker_q.qsize() == 1, f"expected 1 worker chunk, got {worker_q.qsize()}"
    print("[PASS] route_audio_chunk separates caller/worker queues")

    # Cleanup tasks created by route_audio_chunk
    for state in s.audio_channels.values():
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass


async def test_live_transcript_worker_isolation():
    """Worker text via live_transcript must not enter caller extraction."""
    ws = FakeWebSocket()
    s = CallSession(ws, call_id="dual-text")
    s.started = True

    # Caller speaks first
    await _handle_text(s, json.dumps({
        "type": "live_transcript",
        "speaker": "caller",
        "source": "typed",
        "text": "I have a fire at 44 Birchwood Drive.",
        "is_final": True,
    }))
    # Worker speaks (instructional)
    await _handle_text(s, json.dumps({
        "type": "live_transcript",
        "speaker": "worker",
        "source": "typed",
        "text": "Please stay on the line. Do not go back inside.",
        "is_final": True,
    }))

    caller_text = s.caller_final_text
    worker_text = s.worker_final_text
    transcript_for_extraction = s.transcript_for_extraction

    assert "Birchwood" in caller_text, f"caller text missing: {caller_text!r}"
    assert "Birchwood" not in worker_text, f"worker text leaked caller content: {worker_text!r}"
    assert "stay on the line" in worker_text.lower(), f"worker text missing: {worker_text!r}"
    assert "stay on the line" not in transcript_for_extraction.lower(), (
        f"worker speech leaked into caller extraction: {transcript_for_extraction!r}"
    )

    # Dialogue turns should have one of each
    speakers = [t.speaker for t in s.dialogue_turns]
    assert speakers.count("caller") >= 1 and speakers.count("worker") >= 1, speakers
    print("[PASS] live_transcript keeps worker out of caller extraction")


async def test_reset_clears_both_channels():
    ws = FakeWebSocket()
    s = CallSession(ws, call_id="dual-reset")
    s.started = True

    await _handle_text(s, json.dumps({
        "type": "live_transcript",
        "speaker": "caller",
        "source": "typed",
        "text": "first call caller text",
        "is_final": True,
    }))
    await _handle_text(s, json.dumps({
        "type": "live_transcript",
        "speaker": "worker",
        "source": "typed",
        "text": "first call worker text",
        "is_final": True,
    }))
    s.route_audio_chunk("caller", _silence(0.2))
    s.route_audio_chunk("worker", _silence(0.2))

    assert s.dialogue_turns, "dialogue_turns expected non-empty before reset"

    s._reset_call_state()

    assert s.dialogue_turns == [], "dialogue_turns should be empty after reset"
    assert s.caller_final_text == "", "caller text should be empty after reset"
    assert s.worker_final_text == "", "worker text should be empty after reset"
    assert s._dialogue_seq == 0, "dialogue seq should be 0 after reset"
    assert s._next_audio_meta is None, "audio meta should be cleared after reset"
    for speaker, state in s.audio_channels.items():
        assert state.queue.empty(), f"{speaker} queue should be empty after reset"
        assert state.pcm == [], f"{speaker} pcm should be empty after reset"
        assert state.total_samples == 0, f"{speaker} total_samples should be 0"
        assert state.task is None or state.task.done(), f"{speaker} task should be cancelled"
    print("[PASS] _reset_call_state clears both channels + dialogue")


async def test_audio_chunk_meta_pairs_with_next_binary():
    """audio_chunk_meta sets _next_audio_meta consumed by next binary frame."""
    ws = FakeWebSocket()
    s = CallSession(ws, call_id="dual-meta")
    s.started = True

    await _handle_text(s, json.dumps({
        "type": "audio_chunk_meta",
        "speaker": "worker",
        "seq": 1,
    }))
    assert s._next_audio_meta == {"speaker": "worker", "seq": 1}

    # Simulate the binary route consuming the meta
    meta = s._next_audio_meta or {}
    s._next_audio_meta = None
    speaker = meta.get("speaker", "caller")
    s.route_audio_chunk(speaker, _silence(0.2))

    assert s._next_audio_meta is None
    assert s.audio_channels["worker"].queue.qsize() == 1
    assert s.audio_channels["caller"].queue.qsize() == 0
    print("[PASS] audio_chunk_meta paired with next binary frame")

    for state in s.audio_channels.values():
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass


async def main():
    await test_route_audio_chunk_separates_channels()
    await test_live_transcript_worker_isolation()
    await test_reset_clears_both_channels()
    await test_audio_chunk_meta_pairs_with_next_binary()
    print("\nall PASS")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
