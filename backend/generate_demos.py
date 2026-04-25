"""One-time script: pre-synthesize all demo scenarios to MP3 files.

Run once after install:

    python generate_demos.py

Outputs to backend/demo_audio/{scenario_id}.mp3
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import edge_tts

from scenarios import SCENARIOS

OUT_DIR = Path(__file__).parent / "demo_audio"
OUT_DIR.mkdir(exist_ok=True)


async def synthesize_one(scenario) -> Path:
    out = OUT_DIR / f"{scenario.id}.mp3"
    if out.exists():
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
