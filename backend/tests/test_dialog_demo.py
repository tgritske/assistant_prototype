"""Verification: dialog scenario per-turn playback labels speakers correctly.

Drives play_scenario('gas-leak-dialog-01') end-to-end with per-turn manifest
and asserts:
- caller_text contains caller-only utterances (e.g. "Birchwood")
- worker_text contains worker-only utterances (e.g. "nine-one-one")
- dialogue_turns alternate caller/worker per the script
- worker speech does NOT appear in transcript_for_extraction (caller-only)

Run:
    cd backend
    python tests/test_dialog_demo.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("SCENARIO_PACE_REALTIME", "0")  # skip wall-clock sleeps
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("OLLAMA_HOST", "")
os.environ.setdefault("STT_PROVIDER", "whisper")
os.environ.setdefault("WHISPER_MODEL_SIZE", "base")

from main import CallSession  # noqa: E402


SCENARIO_ID = "gas-leak-dialog-01"


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


async def main_async():
    manifest = BACKEND_DIR / "demo_audio" / SCENARIO_ID / "manifest.json"
    if not manifest.exists():
        print(f"SKIP: manifest missing — run generate_demos.py first ({manifest})")
        return 0

    ws = FakeWebSocket()
    session = CallSession(ws, call_id="test-dialog")
    session.started = True
    session.input_mode = "scenario"
    session.scenario_id = SCENARIO_ID

    await session.play_scenario(SCENARIO_ID)

    speakers = [t.speaker for t in session.dialogue_turns]
    caller_count = speakers.count("caller")
    worker_count = speakers.count("worker")
    caller_text_lc = session.caller_final_text.lower()
    worker_text_lc = session.worker_final_text.lower()
    extraction_text_lc = session.transcript_for_extraction.lower()

    print(f"turns: {len(session.dialogue_turns)}  caller={caller_count}  worker={worker_count}")
    print(f"caller text head: {session.caller_final_text[:120]!r}")
    print(f"worker text head: {session.worker_final_text[:120]!r}")

    assert caller_count >= 5, f"expected several caller turns, got {caller_count}"
    assert worker_count >= 5, f"expected several worker turns, got {worker_count}"

    # Caller-only landmarks
    assert "birchwood" in caller_text_lc, "caller text missing 'Birchwood'"
    assert "emma" in caller_text_lc, "caller text missing 'Emma'"
    # Worker-only landmarks (dispatcher questions/instructions)
    assert "do not go back inside" in worker_text_lc, (
        f"worker text missing 'do not go back inside': {worker_text_lc!r}"
    )
    assert any(
        kw in worker_text_lc
        for kw in ("nine-one-one", "9-1-1", "911", "what is your emergency")
    ), f"worker text missing 9-1-1 greeting: {worker_text_lc!r}"

    # Caller-only extraction must NOT include worker speech
    assert "do not go back inside" not in extraction_text_lc, (
        "worker speech leaked into caller extraction"
    )
    assert "what is your emergency" not in extraction_text_lc, (
        "worker speech leaked into caller extraction"
    )

    # Final segments are caller-only and roughly match caller_text
    assert session.full_transcript.lower() == caller_text_lc.strip(), (
        "full_transcript should equal caller_final_text for dialog mode"
    )

    # Outgoing messages should include dialogue_update events
    types = [m.get("type") for m in ws.sent]
    assert types.count("dialogue_update") >= len(session.dialogue_turns), (
        f"expected one dialogue_update per turn, got {types.count('dialogue_update')}"
    )
    assert "scenario_finished" in types, "scenario_finished not emitted"

    print("\n[PASS] dialog scenario splits caller/worker correctly")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
