# Final Plan: Evidence-Only Emergency Dispatch Assistant

This document is written for Codex, Claude Code, or a new engineer rebuilding the assistant from zero. The main product requirement is strict: the assistant may only use information that appears in caller speech or an explicit dispatcher edit. Demo scenario scripts, scenario titles, prompt examples, prior runs, and likely defaults must never fill the form.

## 1. Product Contract

The system is an emergency dispatcher assistant, not an autonomous dispatcher. It should:

- Listen to the caller in real time.
- Transcribe speech as accurately as possible.
- Translate caller speech to English for the worker when needed.
- Classify incident type and priority.
- Fill a structured dispatch form.
- Suggest follow-up questions and pre-arrival instructions.
- Let the worker ask or play generated questions in the caller language.
- Preserve original caller wording for audit/debugging.

Hard rule: every filled field must be grounded in caller transcript evidence, translated transcript evidence, or a dispatcher manual edit.

## 2. Current Technology Stack

Frontend:

- React + TypeScript + Vite.
- Zod for websocket message validation.
- Tailwind-style utility classes with project CSS variables.
- Native WebSocket for JSON events and binary PCM audio.
- Browser `getUserMedia` + `AudioContext` for caller microphone audio.
- Browser `SpeechRecognition` only for worker dictation in English compose mode.

Backend:

- Python FastAPI + Uvicorn.
- WebSocket `/ws` as the realtime session channel.
- `faster-whisper` for local speech-to-text.
- Pydantic schemas for form and websocket payloads.
- Optional LLM backends through a shared `LLMBackend` protocol:
  - Ollama local OpenAI-compatible endpoint.
  - Groq/OpenRouter OpenAI-compatible endpoints.
  - Anthropic Claude.
- `edge-tts` for text-to-speech playback.

Important architectural stance:

- Audio recognition is local and backend-owned.
- LLMs may refine extraction and translation, but cannot bypass evidence validation.
- Local realtime rules provide immediate filling when the LLM is slow or unavailable.
- Demo audio is only an audio source. Scenario scripts are not an extraction source.

## 3. Non-Negotiable Data Boundaries

Do not let these sources fill the form:

- `scenarios.py` script text.
- Scenario title or description.
- Generated demo script files.
- Prompt examples.
- Old call state.
- Model prior knowledge.
- Canned fallback tables.

Allowed sources:

- Recognized caller transcript.
- English operator transcript translated from caller transcript.
- Dispatcher manual edits.
- Protocol/rule templates for suggestions, as long as they do not add case facts.

Protocol templates are allowed for questions like "What is the exact address?" They are not allowed to fill facts like names, addresses, victim counts, cross streets, or occupant identities.

## 4. Backend Pipeline

### 4.1 WebSocket Session

Each websocket connection owns one `CallSession`.

Session state:

- `final_segments`: confirmed transcript segments.
- `provisional_segment`: interim transcript, if applicable.
- `form_state`: current dispatcher form.
- `manual_edits`: fields protected from AI overwrite.
- `ai_filled_fields`: fields filled by the assistant.
- `_field_sources`: whether a field came from interim or final extraction.
- `language`: detected caller language.
- `_operator_transcript_text`: English worker-facing transcript.
- `_call_epoch`: reset guard so stale async tasks cannot update a new call.

On `start_call`:

- Reset all per-call state.
- Mark call active.
- Start audio processor if `input_mode` is `live_audio`.

On `stop_call`:

- Increment epoch.
- Cancel background tasks.
- Clear transcript, form, suggestions, translations, audio buffers, language votes.
- Send `call_ended`.

### 4.2 Audio Ingestion

Frontend sends PCM16 mono chunks over websocket binary frames.

Backend:

- Converts PCM16 to float32.
- Queues chunks in `_audio_queue`.
- Batches enough audio for Whisper.
- Sends the batch to `WhisperService.transcribe_array`.
- Appends returned text as a final transcript segment.

Current default:

- Frontend sends 0.5 second audio chunks.
- Backend batches 3 seconds for live microphone quality.
- Demo playback uses 4 second chunks to preserve addresses and proper nouns.
- Whisper beam size defaults to 5 for better names/streets.

The batching rule matters. Very short chunks are faster, but they split addresses and proper nouns. For the fire demo, 2-second chunks split `1857` from `Pine Ridge Road`; 4-second chunks captured `1857 Pine Ridge Road` together.

### 4.3 Transcription

`services/whisper_service.py` owns the model.

Recommended defaults:

- `WHISPER_MODEL=small` for hackathon speed/quality.
- `WHISPER_BEAM_SIZE=5`.
- `WHISPER_COMPUTE_TYPE=int8`.
- `WHISPER_DEVICE=auto`.

For production:

- Use a true streaming ASR or Whisper large-v3-turbo on GPU.
- Emit word timestamps and confidence.
- Keep a transcript revision model so low-confidence text can be corrected without corrupting confirmed fields.

### 4.4 Translation

Translation is asynchronous and display-oriented first.

Flow:

- Detect caller language from transcript/extraction.
- If non-English, ask active LLM backend to translate transcript to English.
- Store translated text in `operator_transcript`.
- Trigger extraction again on the translated text.

Rules:

- Translation must preserve names, numbers, addresses, and uncertainty.
- Translation output may help extraction.
- Translation output still goes through evidence validation before form fields update.

### 4.5 Extraction

Extraction has two layers:

1. Local realtime extractor in `services/realtime_extractor.py`.
2. Optional LLM extractor in `services/claude_service.py` or `services/openai_compat.py`.

The local extractor:

- Classifies incident type using multilingual emergency phrases.
- Infers priority from explicit life-threat terms.
- Extracts address, caller name, phone, age, victim count, weapons, hazards.
- Generates immediate suggestions for missing critical data.
- Uses only current transcript text.

The LLM extractor:

- Receives the growing transcript only.
- Uses structured tool/function output.
- Must not receive scenario script or demo metadata.
- Must be temperature-low.
- Must be prompted to ignore examples, prior knowledge, scenario titles, and likely defaults.

### 4.6 Normalization and Evidence Gate

`services/form_normalizer.py` is the safety boundary before any form update.

It must:

- Normalize enum casing.
- Normalize phone and integer fields.
- Keep `location` concise.
- Reject full incident narratives in location fields.
- Reject hallucinated addresses, cross streets, and caller names.
- Prefer addresses extracted from transcript over model-proposed addresses.
- Allow partial addresses when the caller only gives a house number.

Examples:

- Transcript says: `The address is 1857. Pine Ridge Road.`
  - Location may be `1857 Pine Ridge Road`.
- Transcript says only: `The address is 1857.`
  - Location may be `1857`.
- Model says: `Popova Street and Oak Avenue`, transcript says only `1857`.
  - Location must stay `1857`; cross street must stay null.
- Model says: `David Kim`, transcript contains `My name is David Kim`.
  - Caller name may be `David Kim`.
- Model says: `Robert Chen`, transcript does not contain it.
  - Caller name must be null.

This is the most important anti-hallucination layer in the backend.

### 4.7 Form Update Semantics

The backend sends `form_update` only after normalization.

Rules:

- Manual dispatcher edits are never overwritten.
- Interim fields may fill blanks but cannot overwrite final fields.
- Final fields may replace interim fields.
- Null from a final pass can clear a previous interim guess.
- AI-filled fields are tracked separately for UI transparency.

### 4.8 Suggestions

Suggestions may be protocol-driven. They should not invent facts.

Good suggestions:

- `What is the exact address?`
- `Is everyone out of the building?`
- `Tell the caller to stay outside and not re-enter.`
- `Is the patient breathing normally?`

Bad suggestions:

- `Ask if Mrs. Patterson is inside` unless Mrs. Patterson was in the transcript.
- `Tell units to respond to Oak Avenue` unless Oak Avenue was in the transcript.

## 5. Frontend Pipeline

### 5.1 Caller Microphone

Use `useAudioCapture`.

Flow:

- `getUserMedia`.
- `AudioContext`.
- Downsample to 16 kHz.
- Convert Float32 to PCM16.
- Send binary frames over websocket.
- Backend owns recognition and language detection.

Do not use browser SpeechRecognition for caller audio as the default. It requires a selected language and can silently bias recognition.

### 5.2 Worker Dictation

Browser SpeechRecognition is acceptable for worker dictation because:

- The worker UI is English.
- The recognizer can be locked to `en-US`.
- It does not create caller transcript facts.

### 5.3 Transcript UI

Show:

- English operator transcript as primary.
- Original caller wording as secondary when different.
- Interim text visually distinct.
- Highlight critical keywords from transcript.

### 5.4 Form UI

Show:

- AI-filled fields with a visible badge.
- Manual edits with protection state.
- Priority and priority reasoning.
- Clear dispatch button requiring confirmation.

The worker should never need to read Russian or another caller language to understand the form.

### 5.5 Caller Communication UI

For non-English calls:

- Show auto-generated questions in English.
- Show the translated phrase that will be played.
- Let worker type or dictate English.
- Backend translates to caller language.
- TTS plays translated speech.

## 6. Build From Zero: Recommended Implementation Order

1. Define schemas first.
   - `FormFields`, `Suggestion`, websocket messages, transcript segments.

2. Build WebSocket session lifecycle.
   - Start, stop, reset, epoch guard, manual edits.

3. Build local audio transcription.
   - Browser PCM16 sender.
   - Backend queue.
   - Whisper service.
   - Transcript updates.

4. Build evidence-only normalization.
   - Address extraction.
   - Name grounding.
   - Cross-street grounding.
   - Narrative rejection for location.

5. Build local realtime extractor.
   - Incident classification.
   - Priority.
   - Critical fields.
   - Suggestions.

6. Add LLM extraction behind the same normalizer.
   - Never let LLM write directly to form state.
   - No concrete address/name examples in prompts.
   - No scenario metadata in prompts.

7. Add translation.
   - Async operator transcript.
   - Extraction rerun on translated transcript.
   - Evidence gate remains mandatory.

8. Add TTS caller communication.
   - English worker prompts.
   - Translation to caller language.
   - TTS playback.

9. Add demo scenarios only as audio fixtures.
   - Scenario scripts can exist for generation.
   - Runtime extraction must never read script content.

10. Add regression tests.
   - Hallucinated location rejection.
   - Partial address retention.
   - Cross-street rejection.
   - Russian address extraction.
   - New-call state isolation.
   - Demo audio transcription chunking.

## 7. Regression Tests To Keep Forever

Minimum backend tests:

- Transcript: `The address is 1857.`
  - LLM says `Popova Street`.
  - Expected location: `1857`.

- Transcript: `The address is 1857. Pine Ridge Road.`
  - Expected location: `1857 Pine Ridge Road`.

- Transcript: `My name is David Kim.`
  - LLM says caller name `Robert Chen`.
  - Expected caller name: null or unchanged unless `Robert Chen` appears in transcript.

- Transcript: Russian `по адресу Попова 12`.
  - Expected location: `Popova Street 12`.

- Stop call, start new call.
  - Expected no transcript, form, suggestions, or background task leakage.

- Scenario playback.
  - Expected extraction based only on recognized transcript.
  - Scenario script is never imported into extraction code.

## 8. Operational Notes

Useful environment variables:

- `WHISPER_MODEL=small`
- `WHISPER_BEAM_SIZE=5`
- `WHISPER_COMPUTE_TYPE=int8`
- `WHISPER_DEVICE=auto`
- `LIVE_WHISPER_CHUNK_SEC=3.0`
- `SCENARIO_WHISPER_CHUNK_SEC=4.0`
- `OLLAMA_MODEL=qwen2.5:7b-instruct`
- `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` if using cloud LLMs.

Run:

```bash
./run.sh
```

Validate:

```bash
python3 -m py_compile backend/main.py backend/prompts.py backend/services/*.py
cd frontend && npm run build
```

## 9. Architecture Summary

The correct architecture is not "LLM listens to the call." The correct architecture is:

```text
Audio
  -> local ASR transcript
  -> original transcript store
  -> optional English translation
  -> local realtime extraction
  -> optional LLM extraction
  -> evidence normalizer
  -> form update / suggestions / priority
  -> worker UI
```

Every path into the form must pass through the evidence normalizer. That one rule keeps the assistant useful without letting it become imaginative in the dangerous places.
