"""Verification test: tail-of-call audio must reach the transcript.

Replays each demo MP3 through the same play_scenario() pipeline the UI uses
and verifies the resulting transcript covers the last ~4 seconds of audio.

Run:
    cd backend
    # Default: tests the current (post-fix) code with the final-pass enabled.
    python tests/test_tail_loss.py

    # Pre-fix baseline: skip the final-pass + run only the streamed chunk
    # loop, to demonstrate how much tail was being lost before the fix.
    python tests/test_tail_loss.py --baseline

    # Single scenario:
    python tests/test_tail_loss.py --scenario fire-structure-01

    # Also exercise live-mic path (queues PCM chunks instead of play_scenario):
    python tests/test_tail_loss.py --mode live
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# Make `backend/` importable when invoked from anywhere
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Skip wall-clock pacing in play_scenario so we don't wait the full audio duration
os.environ.setdefault("SCENARIO_PACE_REALTIME", "0")
# Disable LLM so Claude extraction doesn't run during tests
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("OLLAMA_HOST", "")
os.environ.setdefault("STT_PROVIDER", "whisper")
os.environ.setdefault("WHISPER_MODEL_SIZE", "base")

import numpy as np

from main import CallSession, _decode_mp3_to_pcm
from scenarios import SCENARIOS
from services.whisper_service import SAMPLE_RATE


TAIL_SECONDS = 4.0
WORD_COVERAGE_THRESHOLD = 0.6  # ≥60% of tail-reference words must appear


class FakeWebSocket:
    """Stand-in for FastAPI's WebSocket — captures messages, never raises."""

    class _ClientState:
        name = "CONNECTED"

    def __init__(self):
        self.client_state = self._ClientState()
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


def _normalize_words(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return [w for w in text.split() if w]


def _word_coverage(reference: list[str], actual: list[str]) -> float:
    if not reference:
        return 1.0
    actual_set = set(actual)
    hits = sum(1 for w in reference if w in actual_set)
    return hits / len(reference)


async def _run_scenario_path(scenario_id: str, baseline: bool) -> CallSession:
    """Drive play_scenario() exactly like the WS handler does."""
    if baseline:
        os.environ["SCENARIO_FINAL_PASS"] = "0"
    else:
        os.environ.pop("SCENARIO_FINAL_PASS", None)

    ws = FakeWebSocket()
    session = CallSession(ws, call_id=f"test-{scenario_id}")
    session.started = True
    session.input_mode = "scenario"
    session.scenario_id = scenario_id
    await session.play_scenario(scenario_id)
    return session


async def _run_live_path(scenario_id: str, pcm: np.ndarray, with_flush: bool) -> CallSession:
    """Drive the live-mic path: push PCM into _audio_queue then flush."""
    ws = FakeWebSocket()
    session = CallSession(ws, call_id=f"test-{scenario_id}")
    session.started = True
    session.input_mode = "live_audio"
    session._start_audio_processor()

    chunk_samples = int(0.5 * SAMPLE_RATE)
    cursor = 0
    while cursor < pcm.shape[0]:
        end = min(cursor + chunk_samples, pcm.shape[0])
        await session._audio_queue.put(pcm[cursor:end].astype(np.float32))
        cursor = end
        await asyncio.sleep(0)

    # Wait for the processor to consume what it can (LIVE_MIN_SEC threshold).
    deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.1)
        if session._audio_queue.empty():
            break

    if with_flush:
        await session._flush_pending_audio(session._call_epoch)

    if session._audio_proc_task and not session._audio_proc_task.done():
        session._audio_proc_task.cancel()
        try:
            await session._audio_proc_task
        except asyncio.CancelledError:
            pass

    return session


async def _reference_tail_words(
    session: CallSession, pcm: np.ndarray, language: str
) -> list[str]:
    """Whisper on the last TAIL_SECONDS in isolation = ground truth for the tail."""
    tail = pcm[-int(TAIL_SECONDS * SAMPLE_RATE):]
    lang_hint = language.split("-")[0] if language else None
    segments, _ = await session.transcriber.transcribe_array(
        tail, language=lang_hint, use_vad=False
    )
    text = " ".join(s.text.strip() for s in segments if s.text.strip())
    return _normalize_words(text)


async def main_async(args):
    scenarios = [s for s in SCENARIOS if not args.scenario or s.id == args.scenario]
    if not scenarios:
        print(f"no scenario matches {args.scenario!r}")
        return 1

    print(f"mode={args.mode}  baseline={args.baseline}  "
          f"whisper={os.environ.get('WHISPER_MODEL_SIZE', 'base')}")
    print("─" * 80)

    failures = 0
    for scen in scenarios:
        mp3_path = BACKEND_DIR / "demo_audio" / f"{scen.id}.mp3"
        if not mp3_path.exists():
            print(f"[SKIP] {scen.id}: MP3 missing — run generate_demos.py")
            continue

        pcm = _decode_mp3_to_pcm(str(mp3_path), SAMPLE_RATE)
        duration = pcm.shape[0] / SAMPLE_RATE
        print(f"\n▶ {scen.id}  ({duration:.1f}s, lang={scen.language})")

        if args.mode == "scenario":
            session = await _run_scenario_path(scen.id, baseline=args.baseline)
        else:
            session = await _run_live_path(scen.id, pcm, with_flush=not args.baseline)

        transcript = session.full_transcript
        actual_words = _normalize_words(transcript)
        ref_tail_words = await _reference_tail_words(session, pcm, scen.language)
        coverage = _word_coverage(ref_tail_words, actual_words)
        ok = coverage >= WORD_COVERAGE_THRESHOLD

        # Script-tail comparison gives a human-readable check
        script_words = _normalize_words(scen.script or "")
        if script_words:
            wps = len(script_words) / max(duration, 0.1)
            n_tail = max(8, int(TAIL_SECONDS * wps))
            script_coverage = _word_coverage(script_words[-n_tail:], actual_words)
        else:
            script_coverage = float("nan")

        tag = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1

        print(f"  [{tag}] tail-oracle coverage={coverage:.0%}  "
              f"script-tail coverage={script_coverage:.0%}")
        print(f"    oracle tail: {' '.join(ref_tail_words[-15:])}")
        print(f"    transcript end: ...{transcript[-200:]}")
        if not ok:
            missing = [w for w in ref_tail_words if w not in set(actual_words)]
            print(f"    MISSING: {missing[:20]}")

    print("\n" + "─" * 80)
    print(f"{failures} failure(s)" if failures else "all PASS")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["scenario", "live"],
        default="scenario",
        help="Which pipeline to test. 'scenario' = play_scenario() (UI demo path); "
             "'live' = live-mic _audio_queue path.",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Skip the fix (no final-pass for scenario / no flush for live) "
             "to demonstrate pre-fix tail loss.",
    )
    parser.add_argument("--scenario", help="Run only one scenario id")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
