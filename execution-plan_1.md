# Emergency Dispatcher AI Assistant — Hackathon Plan

## Context

Emergency dispatchers are under extreme cognitive load: they listen to a caller, type into a CAD form, assess priority, decide where to route the call, and often guide the caller through pre-arrival instructions — all simultaneously. Mistakes or delays cost lives. This app reduces data-entry burden by transcribing the call in real time and auto-filling the dispatch form, so the dispatcher can stay focused on the caller and on decision-making. AI suggestions surface protocol reminders (e.g. "caller mentioned chest pain → ask about breathing difficulty") without ever replacing dispatcher judgment. The tool is framed explicitly as an assistant, not a replacement.

---

## Architecture Decision: Self-Hosted Python Stack

**Recommendation: Single Python (FastAPI) server.**

We pivoted from the original Node.js + Deepgram design to a self-hosted Python stack for three domain-specific reasons:

1. **Privacy** — emergency call audio contains PII, medical info, addresses. "Audio never leaves the PSAP" is a strong, accurate pitch. Deepgram is SOC 2 / HIPAA-eligible but vendor processing is still a real concern in public safety.
2. **No API dependency / offline capable** — works without internet, no rate limits, no vendor lock-in.
3. **Multilingual potential** — Piper local TTS enables caller-language responses for non-English callers (stretch goal).

Rationale for a single Python service (not Node + Python split):
- `faster-whisper` and `piper` are Python libraries — no mature Node equivalents for streaming local STT
- Anthropic Python SDK has full parity with the Node SDK (streaming, prompt caching, tool use)
- One service = fewer failure points during a hackathon demo
- FastAPI handles WebSockets natively via Starlette
- Adding a Node layer in front of Python would be pure complexity with no benefit

**LangChain is explicitly NOT needed** — it adds abstraction overhead to a single structured-output prompt pattern.

**When 2 services would make sense (post-hackathon):**
- If STT needs to scale independently of the API orchestration layer
- If deploying multiple GPU instances behind a load balancer
- If adding a local LLM on a separate inference server

For now: one Python FastAPI service handles WebSocket connections, the WhisperLive bridge, Claude API calls, and (stretch) Piper TTS. A second process runs WhisperLive itself on port 9090.

---

## Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + TypeScript + Vite | Fast dev, good DX |
| Styling | Tailwind CSS | Rapid layout without custom CSS |
| WebSocket (client) | Native browser WebSocket | No lib needed |
| Backend | **Python 3.11 + FastAPI + uvicorn** | Native Python for ML libs; excellent WS support |
| Speech-to-text | **WhisperLive + faster-whisper `medium` int8** | Self-hosted streaming ASR, privacy-preserving |
| STT acceleration | **Metal / CoreML on Apple Silicon (M3)** | M3 Neural Engine + GPU give 5–10x realtime inference |
| AI analysis | **Claude API (`claude-sonnet-4-6`) via `anthropic` Python SDK** | Structured JSON output, streaming, prompt caching |
| TTS (stretch) | **Piper** | Fast local multilingual TTS for caller-language responses |
| Audio capture | Browser `MediaRecorder` API | Built-in, no extra deps |
| JSON validation | Zod (frontend) + Pydantic (backend) | Guards malformed Claude output; Pydantic for WS message schemas |

---

## UI Layout

```
┌──────────────────────────────────────────────────────────┐
│  🚨 DISPATCH AI ASSISTANT   [🔒 AUDIO LOCAL]  [● LIVE]   │
├────────────────────┬─────────────────────────────────────┤
│                    │  ⚠️  AI SUGGESTION                   │
│                    │  Caller mentioned chest pain.        │
│   TRANSCRIPT       │  → Ask: difficulty breathing?       │
│   (live, scrolls)  │  → Ask: history of heart issues?    │
│                    ├─────────────────────────────────────┤
│   Caller: "I think │  INCIDENT FORM                      │
│   my husband is    │  Type: [ Medical Emergency ▼]       │
│   having a heart   │  Priority: [ P1 - Critical ▼]       │
│   attack, he has   │  Caller Name: [ John Smith        ] │
│   chest pain and   │  Callback #:  [ 555-0192          ] │
│   cant breathe..."  │  Location:    [ 42 Maple St       ] │
│                    │  Cross St:    [ Oak Ave            ] │
│   [keywords        │  Description: [ Chest pain, 60yo  ] │
│    highlighted]    │  Injuries:    [ Yes ▼]              │
│                    │  Hazards:     [                   ] │
│                    │  Notes:       [                   ] │
│                    ├─────────────────────────────────────┤
│                    │  [ SEND TO CAD SYSTEM →]            │
└────────────────────┴─────────────────────────────────────┘
```

Visual language:
- AI-filled fields: light blue background with small "AI" badge
- Manually edited fields: white background
- Suggestions panel: amber/yellow — clearly advisory
- "AI ASSISTANT" label always visible in header
- **"🔒 AUDIO LOCAL" badge** — surfaces the self-hosted privacy story immediately
- "Send to CAD System" button is prominent but requires dispatcher click — no auto-sending

---

## Data Flow

```
Browser                    Python FastAPI            Local Services
───────                    ──────────────            ──────────────
MediaRecorder
  ↓ PCM/WebM (binary WS frames — no base64)
WS.send()          ──────→ FastAPI WS handler
                            ↓ forward raw audio
                            WhisperLive WS client  →  WhisperLive :9090
                                                      └ faster-whisper (Metal)
                                                  ←── interim transcript (~1–2s)
                            ↓ accumulate transcript
                            ↓ trigger: 15–20 new words OR 500ms silence
                            Anthropic SDK (stream) →  Claude API
                                                  ←── streaming JSON chunks
                            ↓ parse + apply fields incrementally
                            WS.send({
                              transcript_update    ← on every WhisperLive event
                              form_update           ← streams in as Claude responds
                              suggestion
                            })
  ←──────────────────────────
  Update panels (Zod-validated)
```

Key design decisions:
- Audio sent as **binary WebSocket frames** (arraybuffer), not base64 — reduces payload ~33%
- Claude triggered on **WhisperLive interim results**, re-triggered on finals to correct
- Claude response is **streamed** — form fields apply as chunks arrive, not after full JSON completes
- WhisperLive and Claude run **in parallel** — no serial wait between them
- **Trigger strategy**: fire Claude every 15–20 new words OR after 500ms silence
  - Silence-only debounce causes nothing to update during fast continuous speech
  - If a Claude call is in-flight, queue at most one follow-up — no parallel pile-up

**Latency note:** interim transcripts appear in ~1–2s (vs ~100ms for Deepgram). This is dispatcher-appropriate — the form updating correctly matters more than sub-second transcript display. The form can lag audio by ~2s without hurting workflow.

---

## Speech-to-Text (WhisperLive Setup)

```
Model:        faster-whisper `medium` int8 (~1.5 GB)
Acceleration: CoreML / Metal backend on M3 (16 GB RAM confirmed)
Inference:    ~5–10x realtime on M3
```

**WhisperLive server** runs as a second process on port 9090:
- `pip install whisperlive` (or run via Docker image)
- Configure: `--model medium --compute_type int8 --backend faster_whisper`
- Exposes WebSocket accepting raw audio chunks
- Returns interim + final transcripts with timestamps

**FastAPI bridge** (`services/whisper_bridge.py`):
- Opens WebSocket connection to `localhost:9090` on call start
- Forwards audio chunks from browser → WhisperLive
- Receives transcripts and:
  - Forwards to browser immediately (`transcript_update`)
  - Accumulates full transcript and triggers Claude pipeline

**Model warm-up**: run one silent inference at server startup so the first real audio doesn't pay the cold-start cost (~1–2s).

**Privacy wins:**
- Raw audio never leaves localhost
- No vendor has access to PII, medical details, or addresses
- Works offline — demo survives venue WiFi issues

---

## Claude Integration

### Prompt structure

**System prompt** (static, defines role and output contract, marked for caching):
```
You are an emergency dispatch assistant. You receive a live call transcript.
Extract structured information and provide protocol suggestions.
Respond ONLY with valid JSON matching this schema. Never refuse or add commentary.

ALWAYS return all fields. Use null for unknown values.
```

**User prompt** (sent every ~15 words of new content):
```
Current transcript so far:
"""
{fullTranscript}
"""

Return JSON:
{
  "formFields": {
    "incidentType": "medical|fire|police|other|null",
    "priority": "P1|P2|P3|P4|null",
    "callerName": "string|null",
    "callbackNumber": "string|null",
    "location": "string|null",
    "crossStreet": "string|null",
    "description": "string|null",
    "injuriesReported": "yes|no|unknown",
    "hazards": "string|null",
    "notes": "string|null"
  },
  "suggestions": [
    { "trigger": "string", "question": "string", "priority": "high|medium" }
  ],
  "highlightKeywords": ["string"]
}
```

### Streaming

Use `anthropic.messages.stream()` with incremental JSON parsing:

```python
async with anthropic.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=[{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }],
    messages=[{"role": "user", "content": user_prompt}]
) as stream:
    async for text in stream.text_stream:
        # incremental JSON parse + emit form_update events as fields complete
```

- Buffer JSON chunks as they arrive
- Parse and emit each field to the form as soon as its value is complete
- Do not wait for the full JSON object before updating UI — first field can appear ~200ms faster

### Prompt Caching

The system prompt is static — `cache_control: ephemeral` cuts time-to-first-token ~85% on repeat calls. Cache TTL is 5 minutes. Since Claude is called every ~15 words during a call, nearly every call after the first will be a cache hit.

### Key behaviors
- Send full accumulated transcript each time (not just deltas) — Claude has context for better accuracy
- Only update form fields the model returns as non-null — preserve dispatcher edits
- Track which fields were AI-filled vs human-edited; protect human edits from being overwritten
- Suggestions deduplicated by trigger to avoid repeating the same prompt
- Validate Claude's JSON with a **Zod schema** before applying to form state — guards against malformed responses under load
- **Pydantic models** for WebSocket message envelopes on the backend (parallel to Zod on frontend)

---

## Text-to-Speech & Translation (STRETCH GOAL)

Only built if the core pipeline is solid by hour 6. Listed last in the Build Order.

**Use case:** caller does not speak dispatcher's language.

**Flow:**
1. Whisper auto-detects caller language during transcription
2. Claude translates transcript → dispatcher's language for display
3. Dispatcher picks from a pre-translated "common phrases" panel (Claude pre-generates these in caller's language at call start: *"Is anyone hurt?" / "Stay on the line" / "Where are you?"*)
4. Piper synthesizes the selected phrase in caller's language
5. FastAPI streams WAV bytes over WS; browser plays to speaker / phone bridge

**Piper setup:**
- `pip install piper-tts`
- Download voices for top 3–5 languages (es, zh, ar, uk, vi) — ~20 MB each
- Synthesis latency ~100–300 ms for short phrases on M3 CPU
- Multi-speaker voices available for better tone in emergencies

**Why pre-translated phrases vs free typing:** faster for dispatcher, reliable output, avoids translation errors on made-up phrases. Dispatcher can still free-type if needed — Claude translates on demand, Piper synthesizes.

---

## File Structure

```
hackathon/
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # Root layout
│   │   ├── components/
│   │   │   ├── TranscriptPanel.tsx    # Left: live transcript with keyword highlights
│   │   │   ├── FormPanel.tsx          # Right: auto-filling form
│   │   │   ├── SuggestionsPanel.tsx   # Top center: AI protocol suggestions
│   │   │   └── StatusBar.tsx          # Header: call status, AI label, "audio local" badge
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # WebSocket connection + message routing
│   │   │   └── useAudioCapture.ts     # MediaRecorder, binary chunk streaming
│   │   ├── schemas/
│   │   │   └── dispatch.ts            # Zod schemas for WS messages
│   │   └── types/
│   │       └── dispatch.ts            # Shared TypeScript types
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
│
└── backend/
    ├── pyproject.toml                 # or requirements.txt
    ├── main.py                        # FastAPI entry, WS endpoint
    ├── services/
    │   ├── whisper_bridge.py          # WhisperLive WS client wrapper
    │   ├── claude_service.py          # Anthropic SDK, streaming, caching
    │   └── piper_service.py           # TTS (stretch)
    ├── prompts.py                     # System prompt constants
    ├── schemas.py                     # Pydantic WS message models
    └── models/                        # Downloaded Piper voices (gitignored)
```

---

## Demo Mode

For the hackathon presentation, include a **"Simulate Call" button** that:
1. Plays a pre-recorded sample audio file (real 911-style emergency scenario)
2. Streams it through the same pipeline as a live mic
3. Shows the full flow: transcript appears → form fills → suggestions appear

This ensures the demo works regardless of mic availability or nervousness during live demo. Keep both modes: real mic + demo simulation.

Sample scenarios to pre-record or script:
- Medical: chest pain / suspected heart attack
- Fire: house fire with possible trapped occupant
- Police: domestic disturbance
- (Stretch) Spanish-speaking caller reporting a medical emergency — exercises translation flow

---

## Trust & Safety Framing (Important for Hackathon Judges)

- Header always shows "AI ASSISTANT — DISPATCHER MAKES ALL DECISIONS"
- **"🔒 AUDIO LOCAL" badge** — surfaces self-hosted privacy story immediately; click for tooltip explaining raw audio never leaves the machine
- Suggestions panel titled "Protocol Reminders" not "AI Commands"
- Form has visible "AI" badge only on AI-filled fields — dispatcher knows what to verify
- "Send to CAD" requires explicit dispatcher click — never automated
- On-screen disclaimer: "This tool assists, it does not replace dispatcher judgment"

**Honest scoping note:** transcripts (not raw audio) still go to Anthropic for reasoning. A fully-local stack would need a local LLM, but no open model matches Claude for structured JSON extraction within hackathon timeframe. This is an appropriate tradeoff to flag in the pitch: *"audio stays local; structured text is processed by Claude under Anthropic's privacy terms."*

---

## Build Order (Hackathon Sequence)

```
1. Python env + WhisperLive install + medium model download        (45 min)
   - python 3.11 venv, pip install fastapi uvicorn anthropic whisperlive
   - Download faster-whisper medium int8 weights
   - Verify WhisperLive runs standalone, accepts audio, returns text

2. FastAPI WebSocket skeleton + React app scaffold                 (45 min)
   - uvicorn main:app, /ws endpoint
   - Vite + Tailwind, empty three-panel layout

3. Audio capture + WhisperLive bridge                              (60 min)
   - Browser mic → binary WS frames (not base64)
   - FastAPI forwards to WhisperLive, receives interim transcripts
   - Transcripts appear live in browser TranscriptPanel

4. Claude streaming integration with prompt caching                (60 min)
   - anthropic.messages.stream() with cache_control
   - Word-count trigger (15–20 words) + 500ms silence fallback
   - In-flight deduplication (max one queued follow-up)
   - Zod (frontend) + Pydantic (backend) validation on JSON output
   - Form fields update incrementally as chunks arrive

5. UI polish (three-panel layout, AI-badged fields, suggestions)   (60 min)

6. Wire WS messages to React state                                 (45 min)

7. Demo mode (pre-recorded audio playback through same pipeline)   (30 min)

8. Polish (keyword highlighting, trust framing, "🔒 AUDIO LOCAL"    (30 min)
   badge, CAD send button)

── Core complete: ~6.5 h ──

9. STRETCH: Piper TTS + translation flow                           (90 min)
   - pip install piper-tts, download voices for es/zh/ar/uk/vi
   - Claude pre-generates common phrases in caller's language at call start
   - Dispatcher phrase selection → Piper synthesis → WS audio stream → browser playback
```

Total estimate: ~6.5 hours for core demo, ~8 hours if stretch is attempted.

---

## Open Questions / Decisions to Make Before Building

1. **API key**: Anthropic API key available? (Deepgram no longer required.)
2. **Demo audio**: Record or find realistic sample emergency call audio for demo mode. For stretch, need a Spanish-language sample.
3. **Hosting**: Run locally on the M3 Air — no deployment needed. Make sure `uvicorn` + WhisperLive + Vite dev server can all run concurrently (they can — M3 16 GB has headroom).
4. **Stretch decision checkpoint**: at hour 5, evaluate whether core is stable enough to attempt Piper translation, or whether remaining time is better spent polishing core.
5. **Form scope**: Can be reduced if time is tight (drop cross street, hazards, notes) — but the Claude prompt already handles `null`, so leaving all fields in costs nothing.
6. **Piper voice choice** (if stretch): e.g. `es_ES-sharvard-medium` for Spanish.
