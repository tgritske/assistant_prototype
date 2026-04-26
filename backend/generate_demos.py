"""One-time script: pre-synthesize all demo scenarios to MP3 files.

Run once after install:

    python generate_demos.py

Outputs:
- backend/demo_audio/{scenario_id}.mp3   — single mixed track for browser playback
- backend/demo_audio/{scenario_id}/      — per-turn MP3 + manifest.json (dialog scenarios only)
  Used by the backend dual-channel pipeline so caller/worker turns are
  transcribed against the right speaker channel.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import edge_tts

from scenarios import SCENARIOS

OUT_DIR = Path(__file__).parent / "demo_audio"
OUT_DIR.mkdir(exist_ok=True)


# Map scenario speaker labels → channel names used by the runtime backend.
def _to_channel_speaker(label: str) -> str:
    return "caller" if label == "caller" else "worker"


async def synthesize_one(scenario) -> Path:
    out = OUT_DIR / f"{scenario.id}.mp3"
    needs_mixed = not (out.exists() and out.stat().st_size > 0)

    if scenario.dialog:
        return await _synthesize_dialog(scenario, out, needs_mixed=needs_mixed)

    if not needs_mixed:
        print(f"  ✓ {scenario.id} (already exists)")
        return out

    communicate = edge_tts.Communicate(
        text=scenario.script,
        voice=scenario.voice,
        rate=scenario.rate,
        pitch=scenario.pitch,
        volume=scenario.volume,
    )
    await communicate.save(str(out))
    print(f"  ✓ {scenario.id} → {out.name} (rate={scenario.rate} pitch={scenario.pitch})")
    return out


async def _synthesize_dialog(scenario, mixed_out: Path, *, needs_mixed: bool) -> Path:
    """Synthesize each dialog turn separately, build manifest, then mix."""
    turn_dir = OUT_DIR / scenario.id
    turn_dir.mkdir(exist_ok=True)
    manifest_path = turn_dir / "manifest.json"

    manifest = {"scenario_id": scenario.id, "turns": []}
    turn_files: list[Path] = []

    for i, turn in enumerate(scenario.dialog):
        speaker = _to_channel_speaker(turn.speaker)
        if turn.speaker == "caller":
            voice, rate, pitch, volume = (
                scenario.voice,
                scenario.rate,
                scenario.pitch,
                scenario.volume,
            )
        else:
            voice, rate, pitch, volume = scenario.dispatcher_voice, "+0%", "+0Hz", "+0%"

        turn_file = turn_dir / f"turn_{i:02d}_{speaker}.mp3"
        if not (turn_file.exists() and turn_file.stat().st_size > 0):
            communicate = edge_tts.Communicate(
                text=turn.text,
                voice=voice,
                rate=rate,
                pitch=pitch,
                volume=volume,
            )
            await communicate.save(str(turn_file))
        turn_files.append(turn_file)
        manifest["turns"].append(
            {
                "index": i,
                "speaker": speaker,
                "file": turn_file.name,
                "text": turn.text,
                "voice": voice,
            }
        )

    manifest_path.write_text(json.dumps(manifest, indent=2))

    if needs_mixed:
        with open(mixed_out, "wb") as f:
            for tf in turn_files:
                f.write(tf.read_bytes())

    print(
        f"  ✓ {scenario.id} → {mixed_out.name} "
        f"({len(scenario.dialog)} dialog turns, manifest: {manifest_path.relative_to(OUT_DIR)})"
    )
    return mixed_out


async def main():
    print(f"Generating {len(SCENARIOS)} demo scenarios…")
    for s in SCENARIOS:
        try:
            await synthesize_one(s)
        except Exception as e:
            print(f"  X {s.id}: {e}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
