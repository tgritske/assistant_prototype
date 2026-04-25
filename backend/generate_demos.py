"""One-time script: pre-synthesize all demo scenarios to MP3 files.

Run once after install:

    python generate_demos.py

Outputs to backend/demo_audio/{scenario_id}.mp3
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from scenarios import SCENARIOS

OUT_DIR = Path(__file__).parent / "demo_audio"
OUT_DIR.mkdir(exist_ok=True)


async def synthesize_one(scenario) -> Path:
    out = OUT_DIR / f"{scenario.id}.mp3"
    if out.exists() and out.stat().st_size > 0:
        print(f"  ✓ {scenario.id} (already exists)")
        return out

    if scenario.dialog:
        return await _synthesize_dialog(scenario, out)

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


async def _synthesize_dialog(scenario, out: Path) -> Path:
    """Synthesize each dialog turn separately, then byte-concatenate into one MP3."""
    tmp_files: list[Path] = []
    for i, turn in enumerate(scenario.dialog):
        if turn.speaker == "caller":
            voice, rate, pitch, volume = (
                scenario.voice, scenario.rate, scenario.pitch, scenario.volume
            )
        else:
            voice, rate, pitch, volume = scenario.dispatcher_voice, "+0%", "+0Hz", "+0%"

        communicate = edge_tts.Communicate(
            text=turn.text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        tmp = OUT_DIR / f"_{scenario.id}_turn{i:02d}.mp3"
        await communicate.save(str(tmp))
        tmp_files.append(tmp)

    with open(out, "wb") as f:
        for tmp in tmp_files:
            f.write(tmp.read_bytes())
            tmp.unlink()

    print(f"  ✓ {scenario.id} → {out.name} ({len(scenario.dialog)} dialog turns)")
    return out


async def main():
    print(f"Generating {len(SCENARIOS)} demo scenarios…")
    for s in SCENARIOS:
        try:
            await synthesize_one(s)
        except Exception as e:
            print(f"  ✗ {s.id}: {e}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
