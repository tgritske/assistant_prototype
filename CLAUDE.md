# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Style

In all interactions be extremely concise. Sacrifice grammar for the sake of concision.
Never use unicode emojis. This is a serious emergency app.

## Project overview

Real-time emergency dispatcher co-pilot. A FastAPI backend ingests audio (live mic or pre-rendered demo MP3), transcribes it with `faster-whisper` (or Reson8), runs structured extraction + suggestions through an LLM, and streams updates to a React/Vite UI over a single WebSocket. Frontend at `:5173` proxies `/ws`, `/audio`, `/scenarios`, `/tts` to the backend at `:8000` (see `frontend/vite.config.ts`).

## Common commands

Run both services together (recommended):

```bash
bash run.sh          # creates venv, installs deps, generates demo audio if missing, starts both
```

Backend only:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
python generate_demos.py             # regenerate demo MP3s (needs internet for edge-tts)
```

Frontend only:

```bash
cd frontend
npm run dev          # vite dev server on :5173
npm run build        # tsc -b && vite build
npm run lint         # eslint .
```

Backend has one verification harness — `backend/tests/test_tail_loss.py` — that replays demo MP3s through `CallSession` and checks the last ~4s of audio survives transcription. Run from `backend/` after activating the venv:

```bash
python tests/test_tail_loss.py                    # all scenarios, current code
python tests/test_tail_loss.py --baseline         # demonstrate pre-fix tail loss
python tests/test_tail_loss.py --scenario fire-structure-01
python tests/test_tail_loss.py --mode live        # exercise live-mic path
```

The harness stubs `WebSocket` (`FakeWebSocket`), forces `WHISPER_MODEL_SIZE=base`, and sets `SCENARIO_PACE_REALTIME=0` to skip wall-clock pacing. No frontend in the loop; backend changes are otherwise validated by running scenarios end-to-end in the UI. No Python linter wired up.

## Configuration

`backend/.env` (copy from `.env.example`) controls runtime behavior. The most load-bearing knobs:

- `LLM_BACKEND=auto|claude|ollama|none` — `auto` prefers Claude, falls back to Ollama, then to rule-based extraction.
- `ANTHROPIC_API_KEY` — required for Claude. The factory rejects placeholder-looking keys (see `_looks_like_real_key` in `services/llm_backend.py`).
- `STT_PROVIDER=whisper|reson8` — local faster-whisper vs. Reson8 cloud streaming.
- `WHISPER_MODEL`, `WHISPER_COMPUTE_TYPE`, `WHISPER_DEVICE`, `WHISPER_BEAM_SIZE` — Whisper tuning.
- `LIVE_WHISPER_CHUNK_SEC` (default 3.0) — minimum live-mic audio before invoking Whisper. Smaller = faster UI updates but worse transcription of proper nouns.

## Architecture

### Single WebSocket, single session per connection

`backend/main.py` is the entry point. Everything realtime flows through one `WS /ws`. The `CallSession` class (`main.py:147`) owns all per-call state: transcript segments, form state, AI-filled vs. dispatcher-edited fields, pending audio buffer, language votes, and async tasks for extraction and translation.

Key mechanisms inside `CallSession`:

- **Trigger-based extraction.** Claude (or fallback) is re-invoked when either (a) the transcript grows by `WORD_COUNT_TRIGGER` words, or (b) `SILENCE_TRIGGER_SEC` of silence has passed since the last new speech. `_schedule_claude` debounces via `_claude_task` + `_claude_rerun_queued`.
- **Two-layer extraction.** `services/realtime_extractor.py` runs first as a fast deterministic pass so the form fills immediately; the LLM result then refines/overrides it via `_apply_extraction`. This means heuristic regexes in `realtime_extractor.py` and `form_normalizer.py` are part of the user-visible behavior, not just a fallback.
- **Manual-edit protection.** Any field the dispatcher has edited is added to `manual_edits` and never overwritten by subsequent LLM passes. AI-filled fields are tracked separately in `ai_filled_fields` for UI highlighting.
- **Call epochs.** `_call_epoch` is incremented on every reset; long-running async tasks capture the epoch on entry and discard their result if it changed. This is the canonical way to avoid stale LLM/translation responses landing in a new call — preserve this pattern when adding new async work.
- **Operator translation.** When the caller's language isn't English, `_run_translation_once` produces an English "operator view" of the transcript. The LLM extracts from the translated text. Don't run translation before a language has been detected (`_should_translate_operator_view` enforces this).

### LLM backend abstraction

`services/llm_backend.py` defines the `LLMBackend` protocol (`extract`, `translate_text`, `translate_phrases`, plus `name`/`model`). `build_backend()` resolves a single backend at startup; `services/claude_service.py` and `services/openai_compat.py` (used for Ollama via the OpenAI-compatible endpoint) implement it. To add a provider, conform to the protocol and register it in `_try_build`.

### Transcription abstraction

`services/transcriber.py` selects between `whisper_service` (local `faster-whisper`) and `reson8_service` (cloud streaming WS) based on `STT_PROVIDER`. Both expose `transcribe_array` / `transcribe_file`. Whisper models are cached under `backend/models/`.

### Frontend

Single `App.tsx` lays out a 4-column grid: scenario picker, transcript, suggestions+translation, and dispatch form. State is centralized in `useCallState`; the WebSocket lives in `useDispatchSocket` (auto-reconnects with backoff and uses a 50ms StrictMode guard before opening). Server messages are validated through Zod schemas in `src/types/dispatch.ts` before reaching state — keep that schema in sync with `backend/schemas.py` server-side message envelopes when adding new message types.

Mic capture has two implementations: `useAudioCapture` (MediaRecorder/PCM upload) and `useWebSpeechCapture` (browser Web Speech API). Audio frames are sent as binary WS messages; control messages are JSON.

## Things to know before changing code

- Demo scenarios in `backend/scenarios.py` are pre-rendered to MP3 by `generate_demos.py` using edge-tts and replayed through the *same* Whisper+LLM pipeline as live audio. So changes to the realtime pipeline affect demo behavior identically.
- `services/form_normalizer.py` contains language-specific address regexes (English + Russian/Ukrainian patterns). Language detection is single-source-of-truth from Whisper/LLM (see recent commits). Don't reintroduce parallel detection.
- Prompts for Claude live in `backend/prompts.py`.
- The WS server expects PCM-16 little-endian audio at the sample rate in `audio_meta`; `whisper_service.SAMPLE_RATE` is the canonical 16 kHz.
- Two env knobs gate the tail-flush fix verified by `test_tail_loss.py`: `SCENARIO_FINAL_PASS` (off → demo path drops the trailing chunk) and `_flush_pending_audio` on the live path. If you refactor `play_scenario` or the live-audio queue, re-run `test_tail_loss.py --baseline` vs default to confirm both paths still capture the tail.
