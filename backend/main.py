"""FastAPI entry point for the Emergency Dispatcher AI Assistant.

Exposes:
- GET  /              → health check
- GET  /scenarios     → list demo scenarios
- GET  /audio/{id}    → serve pre-synthesized MP3 for a scenario
- WS   /ws            → main bidirectional channel (live + demo modes)
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from scenarios import SCENARIOS, get_scenario, scenarios_summary
from schemas import (
    ClaudeExtraction,
    TranscriptSegment,
)
from services.form_normalizer import normalize_extraction
from services.llm_backend import LLMBackend, build_backend
from services.realtime_extractor import extract_realtime_signal
from services.tts_service import COMMON_DISPATCHER_PHRASES, get_tts_service
from services.transcriber import get_transcriber
from services.whisper_service import SAMPLE_RATE

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("dispatch")

BASE_DIR = Path(__file__).parent
DEMO_DIR = BASE_DIR / "demo_audio"

# How often to re-run the Claude extraction — one of these triggers fires it.
WORD_COUNT_TRIGGER = 2   # new words since last extraction pass
SILENCE_TRIGGER_SEC = 0.3  # seconds of silence since last new speech
MIN_CLAUDE_INTERVAL_SEC = 1.5  # hard floor between consecutive Claude calls

# Minimum new audio before calling Whisper for live mic. Shorter chunks feel
# faster but often drop street names and proper nouns; 3s is the current
# quality/latency tradeoff for local faster-whisper on noisy microphone audio.
LIVE_MIN_SEC = float(os.environ.get("LIVE_WHISPER_CHUNK_SEC", "3.0"))

app = FastAPI(title="Emergency Dispatch AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Lazy singletons ──────────────────────────────────────────────────────

_llm: Optional[LLMBackend] = None
_llm_resolved = False


def get_llm() -> Optional[LLMBackend]:
    """Return the active LLM backend, or None if none is available.

    Backend choice is resolved once at first use and cached. To pick a
    different backend, change env vars and restart the server.
    """
    global _llm, _llm_resolved
    if not _llm_resolved:
        _llm = build_backend()
        _llm_resolved = True
    return _llm


# ─── Static endpoints ─────────────────────────────────────────────────────


@app.get("/")
def root():
    return {
        "service": "Emergency Dispatch AI Assistant",
        "status": "ok",
        "scenarios": len(SCENARIOS),
    }


@app.get("/scenarios")
def list_scenarios():
    return {"scenarios": scenarios_summary()}


@app.get("/llm_info")
def llm_info():
    backend = get_llm()
    if backend is None:
        return {"backend": None, "model": None, "mode": "local_rules"}
    return {"backend": backend.name, "model": backend.model, "mode": "live"}


@app.get("/audio/{scenario_id}")
def get_audio(scenario_id: str):
    scen = get_scenario(scenario_id)
    if scen is None:
        return JSONResponse({"error": "unknown scenario"}, status_code=404)
    path = DEMO_DIR / f"{scenario_id}.mp3"
    if not path.exists():
        return JSONResponse(
            {"error": "audio not generated yet — run generate_demos.py"},
            status_code=404,
        )
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/tts")
async def tts_endpoint(text: str, language: str = "en-US"):
    """Synthesize arbitrary text in the requested language. Returns MP3."""
    tts = get_tts_service()
    try:
        audio = await tts.synthesize(text, language)
    except Exception as e:
        log.exception("TTS failed")
        return JSONResponse({"error": str(e)}, status_code=500)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


# ─── WebSocket session ────────────────────────────────────────────────────


class CallSession:
    """State for a single call on the WebSocket.

    Responsible for:
    - accumulating full transcript across Whisper invocations
    - deciding when to invoke Claude (word-count and silence triggers)
    - protecting dispatcher-edited fields from being overwritten
    - streaming updates back to the client
    """

    def __init__(self, ws: WebSocket, call_id: str):
        self.ws = ws
        self.session_id = call_id
        self.call_id = call_id
        self.started = False
        self.scenario_id: Optional[str] = None
        self.final_segments: list[TranscriptSegment] = []
        self.provisional_segment: Optional[TranscriptSegment] = None
        self.last_claude_word_count = 0
        self.last_audio_time = time.monotonic()
        self.manual_edits: set[str] = set()
        self.form_state: dict = {}
        self.ai_filled_fields: set[str] = set()
        self._field_sources: dict[str, Literal["interim", "final"]] = {}
        self.suggestions_seen: set[str] = set()
        self.language: Optional[str] = None
        self.input_mode: Literal["live_text", "live_audio", "scenario"] = "live_text"
        self.llm: Optional[LLMBackend] = get_llm()
        self.transcriber = get_transcriber()
        self.tts = get_tts_service()
        self._claude_task: Optional[asyncio.Task] = None
        self._claude_rerun_queued = False
        self._last_claude_started_time: float = 0.0
        self._llm_ok: Optional[bool] = None  # None=unknown, True=alive, False=failing
        # Live-mic pending-audio buffer (cleared after each transcription — no overlap)
        self._live_pcm: list[np.ndarray] = []
        self._live_total_samples: int = 0   # samples in pending buffer
        self._live_transcribed_samples: int = 0  # cumulative samples transcribed (for timestamps)
        self._lang_votes: dict[str, int] = {}  # language detection votes
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        self._audio_proc_task: Optional[asyncio.Task] = None
        self._scenario_task: Optional[asyncio.Task] = None
        self._translation_task: Optional[asyncio.Task] = None
        self._translation_rerun_queued = False
        self._operator_transcript_text: str = ""
        self._operator_interim_text: str = ""
        # Epoch incremented on every session reset; async tasks check it to
        # detect stale results and discard them instead of updating the new call.
        self._call_epoch: int = 0

    # ─── sending ──
    async def send(self, payload: dict):
        try:
            await self.ws.send_json(payload)
        except Exception as e:
            msg = str(e)
            if "websocket.close" in msg or "response already completed" in msg:
                return
            log.warning("WS send failed: %s", e)

    # ─── core pipeline ──
    @property
    def full_transcript(self) -> str:
        return " ".join(s.text.strip() for s in self.final_segments if s.text.strip())

    @property
    def interim_text(self) -> str:
        if self.provisional_segment is None:
            return ""
        return self.provisional_segment.text.strip()

    @property
    def transcript_for_extraction(self) -> str:
        parts = [self.full_transcript, self.interim_text]
        return " ".join(part for part in parts if part).strip()

    @property
    def operator_transcript_for_extraction(self) -> str:
        parts = [self.operator_transcript, self.operator_interim_text]
        return " ".join(part for part in parts if part).strip()

    @property
    def operator_transcript(self) -> str:
        return self._operator_transcript_text or self.full_transcript

    @property
    def operator_interim_text(self) -> str:
        return self._operator_interim_text or self.interim_text

    def _should_translate_operator_view(self) -> bool:
        if not self.language:
            # Defer until Whisper / Claude has emitted a language; running a
            # translation pass before then risks spurious panel mounts.
            return False
        return not self.language.lower().startswith("en")

    def _schedule_translation(self):
        if not self.started:
            return
        if not self._should_translate_operator_view():
            self._operator_transcript_text = self.full_transcript
            self._operator_interim_text = self.interim_text
            return
        if self.llm is None:
            self._operator_transcript_text = self.full_transcript
            self._operator_interim_text = self.interim_text
            return
        if self._translation_task and not self._translation_task.done():
            self._translation_rerun_queued = True
            return
        self._translation_task = asyncio.create_task(self._run_translation_once())

    async def _run_translation_once(self):
        epoch = self._call_epoch
        full_text = self.full_transcript
        interim_text = self.interim_text
        source_language = self.language
        try:
            if not self.started or not self.llm:
                return
            translated_full = full_text
            translated_interim = interim_text
            if full_text.strip():
                translated_full = await self.llm.translate_text(
                    "English", full_text, source_language=source_language
                )
            if interim_text.strip():
                translated_interim = await self.llm.translate_text(
                    "English", interim_text, source_language=source_language
                )
            if self._call_epoch != epoch or not self.started:
                return
            self._operator_transcript_text = translated_full
            self._operator_interim_text = translated_interim
            await self.send(
                {
                    "type": "transcript_update",
                    "segments": [s.model_dump() for s in self.final_segments[-5:]],
                    "full_text": self.full_transcript,
                    "interim_text": self.interim_text or None,
                    "operator_text": self.operator_transcript,
                    "operator_interim_text": self.operator_interim_text or None,
                    "language": self.language,
                }
            )
            if self.operator_transcript_for_extraction.strip():
                self._schedule_claude()
        finally:
            if self._call_epoch == epoch and self._translation_rerun_queued:
                self._translation_rerun_queued = False
                self._translation_task = asyncio.create_task(self._run_translation_once())
            else:
                self._translation_task = None

    def _word_count(self, s: str) -> int:
        return len([w for w in s.split() if w])

    def _should_fire_claude(self, forced: bool = False) -> bool:
        if forced:
            return True
        if time.monotonic() - self._last_claude_started_time < MIN_CLAUDE_INTERVAL_SEC:
            return False
        wc = self._word_count(self.transcript_for_extraction)
        if wc - self.last_claude_word_count >= WORD_COUNT_TRIGGER:
            return True
        if (
            (self.final_segments or self.provisional_segment)
            and time.monotonic() - self.last_audio_time >= SILENCE_TRIGGER_SEC
            and wc > self.last_claude_word_count
        ):
            return True
        return False

    def _schedule_claude(self, forced: bool = False):
        if not self.started:
            return
        if not self._should_fire_claude(forced) and not forced:
            return
        if self._claude_task and not self._claude_task.done():
            self._claude_rerun_queued = True
            return
        self._claude_task = asyncio.create_task(self._run_claude_once())

    async def _run_claude_once(self):
        epoch = self._call_epoch  # capture on entry; changes when session resets
        self._last_claude_started_time = time.monotonic()
        try:
            if not self.started:
                return
            transcript = self.transcript_for_extraction
            if not transcript.strip():
                return
            source_kind: Literal["interim", "final"] = (
                "interim" if self.provisional_segment is not None else "final"
            )
            self.last_claude_word_count = self._word_count(transcript)

            translated_transcript = self.operator_transcript_for_extraction
            lang_is_english = not self.language or self.language.lower().startswith("en")

            # Run the fast heuristic on the raw transcript only when the language is
            # English (or still unknown). The English-tuned regexes produce nothing
            # useful on foreign text and can overwrite interim fields with blanks.
            # For non-English, wait for the translated operator transcript instead.
            if lang_is_english or not translated_transcript.strip():
                heuristic = extract_realtime_signal(transcript, self.form_state)
                await self._apply_extraction(heuristic, source_kind)

            if (
                translated_transcript.strip()
                and translated_transcript.strip() != transcript.strip()
            ):
                translated_heuristic = extract_realtime_signal(
                    translated_transcript, self.form_state
                )
                await self._apply_extraction(translated_heuristic, source_kind)
            if self._call_epoch != epoch or not self.started:
                return

            result = None
            if self.llm is not None:
                llm_transcript = (
                    translated_transcript
                    if translated_transcript.strip()
                    else transcript
                )
                log.info(
                    "[llm:%s] extracting from %d words",
                    self.llm.name,
                    self.last_claude_word_count,
                )
                result = await self.llm.extract(llm_transcript)

            if self._call_epoch != epoch:
                return  # discard stale LLM result — it belongs to the old call

            if result is not None:
                if self._llm_ok is not True:
                    self._llm_ok = True
                await self._apply_extraction(result, source_kind)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("[%s] extraction pipeline failed: %s", self.call_id, e)
        finally:
            # Only re-queue within the same call epoch; cancellation / reset must
            # not spawn a fresh task that writes to the newly started call.
            if self._call_epoch == epoch and self._claude_rerun_queued:
                self._claude_rerun_queued = False
                self._claude_task = asyncio.create_task(self._run_claude_once())

    async def _apply_extraction(
        self, ex: ClaudeExtraction, source_kind: Literal["interim", "final"]
    ):
        if not self.started:
            return
        ex = normalize_extraction(
            ex,
            source_text=self.transcript_for_extraction,
            operator_text=self.operator_transcript_for_extraction,
            language=self.language,
        )
        # Form fields — preserve manual edits, only overwrite null → value, or value → new value.
        incoming = ex.form_fields.model_dump(exclude_unset=False)
        updated: dict = {}
        for field, value in incoming.items():
            if field in self.manual_edits:
                continue

            current_source = self._field_sources.get(field)

            if source_kind == "interim":
                # Keep interim updates low-risk: they can populate blank fields or
                # revise earlier interim values, but they must not overwrite values
                # already confirmed by a final transcript pass.
                if current_source == "final" or value is None:
                    continue
                if self.form_state.get(field) != value or current_source != "interim":
                    self.form_state[field] = value
                    self._field_sources[field] = "interim"
                    updated[field] = value
                    self.ai_filled_fields.add(field)
                continue

            if value is None:
                # Final transcript corrected away a previously provisional guess.
                if current_source == "interim" and field in self.form_state:
                    self.form_state.pop(field, None)
                    self._field_sources.pop(field, None)
                    self.ai_filled_fields.discard(field)
                    updated[field] = None
                continue

            if self.form_state.get(field) != value or current_source != "final":
                self.form_state[field] = value
                self._field_sources[field] = "final"
                updated[field] = value
                self.ai_filled_fields.add(field)

        if updated:
            await self.send(
                {
                    "type": "form_update",
                    "fields": updated,
                    "ai_filled_fields": sorted(self.ai_filled_fields),
                }
            )

        # Priority broadcast (always)
        if self.form_state.get("priority"):
            await self.send(
                {
                    "type": "priority_update",
                    "priority": self.form_state["priority"],
                    "reasoning": ex.priority_reasoning,
                }
            )

        # Suggestions — dedupe by id
        fresh = [s for s in ex.suggestions if s.id not in self.suggestions_seen]
        for s in fresh:
            self.suggestions_seen.add(s.id)
        if ex.suggestions:
            # send the full current set, not just fresh, so UI can reorder
            await self.send(
                {
                    "type": "suggestions",
                    "suggestions": [s.model_dump() for s in ex.suggestions],
                }
            )

        # Highlights
        if ex.highlight_keywords:
            await self.send(
                {"type": "highlights", "keywords": ex.highlight_keywords}
            )

        # Language detection → kick off phrase translation
        if ex.detected_language and ex.detected_language != self.language:
            self.language = ex.detected_language
            await self._handle_language_change(ex.detected_language)
            self._schedule_translation()

    async def _handle_language_change(self, lang: str):
        if not self.started:
            return
        await self.send(
            {
                "type": "language_detected",
                "language": lang,
                "language_name": _lang_name(lang),
            }
        )
        if lang.lower().startswith("en"):
            return
        # Translate common phrases for caller-language playback. If no LLM
        # is available, send the English originals so the panel still works.
        translated: list[str]
        if self.llm is not None:
            try:
                translated = await self.llm.translate_phrases(
                    _lang_name(lang), COMMON_DISPATCHER_PHRASES
                )
            except Exception as e:
                log.warning("phrase translation failed: %s", e)
                translated = COMMON_DISPATCHER_PHRASES
        else:
            translated = COMMON_DISPATCHER_PHRASES
        phrases = [
            {"en": en, "translated": tr}
            for en, tr in zip(COMMON_DISPATCHER_PHRASES, translated)
        ]
        await self.send({"type": "phrases_ready", "language": lang, "phrases": phrases})

    # ─── audio → STT ──

    def _start_audio_processor(self):
        """Cancel any running audio processor and start a fresh one."""
        if self._audio_proc_task and not self._audio_proc_task.done():
            self._audio_proc_task.cancel()
        self._audio_proc_task = asyncio.create_task(self._audio_processor_loop())

    async def _audio_processor_loop(self):
        """Single persistent task: drain audio queue → transcribe → append.

        Key design decisions vs the previous rolling-window approach:
        ─ NO re-transcription of old audio. We keep a pointer (_live_transcribed_samples)
          and only pass NEW audio to Whisper each iteration. This eliminates the
          "My name is House and Fox / House and Fire / Haos and Fire" repetition
          artifacts that happened when the same audio was re-transcribed with a
          shifted window and _merge_incremental failed to reconcile the difference.
        ─ initial_prompt: the last 30 words of the confirmed transcript are fed back
          to Whisper as a text prefix so it (a) continues grammar correctly at chunk
          boundaries, (b) spells names/places consistently, (c) stays in the right
          language even on short clips.
        ─ use_vad=False: the frontend already gates silence via RMS threshold.
          Whisper's internal VAD aggressively trims short live-mic chunks and can
          cut off the first/last syllable of a word.
        ─ Language voting: 2 consistent detections required before locking so a
          single noisy chunk can't permanently lock the wrong language.
        ─ Epoch guard: stale results from a previous call are silently dropped.
        """
        epoch = self._call_epoch
        # Minimum NEW audio before we bother calling Whisper.
        CHUNK_MIN = int(LIVE_MIN_SEC * SAMPLE_RATE)

        try:
            while True:
                # Wait for the first chunk; timeout lets us check epoch regularly
                try:
                    pcm = await asyncio.wait_for(self._audio_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if self._call_epoch != epoch:
                        return
                    continue

                if self._call_epoch != epoch:
                    return

                self.last_audio_time = time.monotonic()

                # Drain any additional chunks that queued up while we were busy
                new_chunks = [pcm]
                while not self._audio_queue.empty():
                    new_chunks.append(self._audio_queue.get_nowait())

                # Accumulate into the pending buffer
                for chunk in new_chunks:
                    self._live_pcm.append(chunk)
                    self._live_total_samples += chunk.shape[0]

                # Not enough audio yet — wait for more chunks
                if self._live_total_samples < CHUNK_MIN:
                    continue

                # Snapshot and clear the pending buffer so the NEXT iteration
                # starts fresh (no overlap → no re-transcription artifacts).
                audio_chunk = np.concatenate(self._live_pcm)
                self._live_pcm.clear()
                self._live_total_samples = 0
                self._live_transcribed_samples += audio_chunk.shape[0]

                # Language hint (base code only, e.g. "ru" not "ru-RU")
                lang_hint: Optional[str] = None
                if self.language:
                    lang_hint = self.language.split("-")[0]

                # Last 30 words give Whisper sentence context and spelling cues
                prompt = " ".join(self.full_transcript.split()[-30:]) or None

                segments, detected_lang = await self.transcriber.transcribe_array(
                    audio_chunk,
                    language=lang_hint,
                    initial_prompt=prompt,
                    use_vad=False,
                )

                if self._call_epoch != epoch:
                    return  # session reset during Whisper inference → discard

                # Require 2 consistent detections before locking language so a
                # single noisy chunk can't permanently lock the wrong language.
                if detected_lang and not self.language:
                    self._lang_votes[detected_lang] = (
                        self._lang_votes.get(detected_lang, 0) + 1
                    )
                    top = max(self._lang_votes, key=lambda k: self._lang_votes[k])
                    if self._lang_votes[top] >= 2:
                        self.language = top
                        log.info("[%s] language locked → %s", self.call_id, top)

                if not segments:
                    continue

                new_text = " ".join(
                    s.text.strip() for s in segments if s.text.strip()
                )
                if not new_text.strip():
                    continue

                # Straight append — no merge needed since there is no overlap
                t_end = self._live_transcribed_samples / SAMPLE_RATE
                ts_seg = TranscriptSegment(
                    text=new_text,
                    start=max(0.0, t_end - audio_chunk.shape[0] / SAMPLE_RATE),
                    end=t_end,
                    is_final=True,
                )
                self.final_segments.append(ts_seg)
                await self.send(
                    {
                        "type": "transcript_update",
                        "segments": [s.model_dump() for s in self.final_segments[-5:]],
                        "full_text": self.full_transcript,
                        "interim_text": None,
                        "operator_text": self.operator_transcript,
                        "operator_interim_text": None,
                        "language": self.language,
                    }
                )
                self._schedule_translation()
                self._schedule_claude()

        except asyncio.CancelledError:
            return

    # ─── demo playback ──
    async def play_scenario(self, scenario_id: str):
        """Stream a pre-synthesized scenario through the same pipeline.

        We decode the MP3 to 16kHz mono PCM, chunk it into ~1s slices,
        and feed each slice through Whisper at realtime speed. The client
        receives audio bytes for playback in sync, so the judges hear the
        "call" while the transcript + form populate.

        The MP3 is decoded in a thread pool while the browser is already
        loading/buffering the audio URL, so both sides start at roughly the
        same moment and the transcript stays in sync with what you hear.
        """
        epoch = self._call_epoch
        scen = get_scenario(scenario_id)
        if scen is None:
            await self.send({"type": "error", "message": f"unknown scenario {scenario_id}"})
            return
        path = DEMO_DIR / f"{scenario_id}.mp3"
        if not path.exists():
            await self.send(
                {"type": "error", "message": "Audio not generated — run generate_demos.py"}
            )
            return

        # Kick off the (blocking) MP3 decode in a thread pool so the event
        # loop stays responsive. Simultaneously, tell the browser to start
        # loading the audio — by the time decode finishes the browser will
        # have buffered the first few hundred ms, keeping us in sync.
        decode_task = asyncio.create_task(
            asyncio.to_thread(_decode_mp3_to_pcm, str(path), SAMPLE_RATE)
        )
        await self.send(
            {
                "type": "scenario_playback",
                "scenario_id": scenario_id,
                "audio_url": f"/audio/{scenario_id}",
                "language": scen.language,
                "title": scen.title,
            }
        )
        pcm = await decode_task
        if self._call_epoch != epoch or not self.started or self.scenario_id != scenario_id:
            return
        total = pcm.shape[0]
        total_sec = total / SAMPLE_RATE

        # Incremental transcription, paced to wall clock, with no overlap.
        # The previous overlapping-window approach could surface words from the
        # next phrase early and produced repeated / mutated fragments.
        STEP_SEC = float(os.environ.get("SCENARIO_WHISPER_CHUNK_SEC", "4.0"))
        language_hint: Optional[str] = scen.language.split("-")[0] if scen.language else None
        cursor_sec = 0.0

        while cursor_sec < total_sec:
            next_cursor = min(cursor_sec + STEP_SEC, total_sec)
            start_sample = int(cursor_sec * SAMPLE_RATE)
            end_sample = int(next_cursor * SAMPLE_RATE)
            chunk = pcm[start_sample:end_sample]
            prompt = " ".join(self.full_transcript.split()[-30:]) or None

            # Run the pacing sleep + transcription in parallel so total wall
            # time per step == max(STEP_SEC, inference_time) instead of sum.
            sleep_task = asyncio.create_task(asyncio.sleep(STEP_SEC))
            transcribe_task = asyncio.create_task(
                self.transcriber.transcribe_array(
                    chunk,
                    language=language_hint,
                    initial_prompt=prompt,
                    use_vad=False,
                )
            )
            await sleep_task
            segments, lang = await transcribe_task
            if self._call_epoch != epoch or not self.started or self.scenario_id != scenario_id:
                return

            if lang and language_hint is None:
                language_hint = lang  # lock after first detection — faster

            new_text = " ".join(s.text.strip() for s in segments if s.text.strip())
            if new_text.strip():
                self.final_segments.append(
                    TranscriptSegment(
                        text=new_text,
                        start=cursor_sec,
                        end=next_cursor,
                        is_final=True,
                    )
                )
                await self.send(
                    {
                        "type": "transcript_update",
                        "segments": [
                            self.final_segments[-1].model_dump()
                        ],
                        "full_text": self.full_transcript,
                        "interim_text": None,
                        "operator_text": self.operator_transcript,
                        "operator_interim_text": None,
                        "language": lang,
                    }
                )
                self._schedule_translation()
                self.last_audio_time = time.monotonic()
                self._schedule_claude()

            cursor_sec = next_cursor

        # Mop-up pass
        await asyncio.sleep(0.2)
        if self._call_epoch != epoch or not self.started or self.scenario_id != scenario_id:
            return
        self._schedule_claude(forced=True)
        await self.send({"type": "scenario_finished", "scenario_id": scenario_id})

    def _cancel_background_tasks(self):
        """Cancel any running Claude extraction and audio processor tasks."""
        if self._claude_task and not self._claude_task.done():
            self._claude_task.cancel()
        self._claude_task = None
        self._claude_rerun_queued = False
        if self._audio_proc_task and not self._audio_proc_task.done():
            self._audio_proc_task.cancel()
        self._audio_proc_task = None
        if self._scenario_task and not self._scenario_task.done():
            self._scenario_task.cancel()
        self._scenario_task = None
        if self._translation_task and not self._translation_task.done():
            self._translation_task.cancel()
        self._translation_task = None
        self._translation_rerun_queued = False

    def _reset_call_state(self):
        """Increment epoch and wipe per-call state so the next call starts clean."""
        self._call_epoch += 1
        self._cancel_background_tasks()
        self.call_id = uuid.uuid4().hex[:8]
        self.started = False
        self.scenario_id = None
        self.final_segments.clear()
        self.provisional_segment = None
        self.form_state.clear()
        self.ai_filled_fields.clear()
        self._field_sources.clear()
        self.manual_edits.clear()
        self.suggestions_seen.clear()
        self._llm_ok = None
        self.last_claude_word_count = 0
        self._last_claude_started_time = 0.0
        self.language = None
        self.input_mode = "live_text"
        self._operator_transcript_text = ""
        self._operator_interim_text = ""
        self._live_pcm.clear()
        self._live_total_samples = 0
        self._live_transcribed_samples = 0
        self._lang_votes.clear()
        # Drain any leftover audio from the old call
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()

    async def stop(self):
        self._reset_call_state()
        if self.ws.client_state.name == "CONNECTED":
            await self.send({"type": "call_ended"})


def _merge_incremental(existing: str, window_text: str) -> str:
    """Return the portion of `window_text` that isn't already at the end of `existing`.

    Whisper retranscribes the last ~1s of overlap each pass, so the window
    often begins with words we already emitted. We find the largest suffix
    of `existing` (up to 25 words) whose lowercased word sequence matches
    the prefix of `window_text`, and return only the rest.
    """
    if not window_text.strip():
        return ""
    if not existing.strip():
        return window_text.strip()

    # Tokenize to lowercase words without punctuation for robust matching.
    def norm(tok: str) -> str:
        return "".join(c for c in tok.lower() if c.isalnum())

    existing_words_raw = existing.split()
    new_words_raw = window_text.split()
    existing_norm = [norm(w) for w in existing_words_raw]
    new_norm = [norm(w) for w in new_words_raw]

    max_check = min(len(existing_norm), len(new_norm), 25)
    best_overlap = 0
    for n in range(max_check, 0, -1):
        if existing_norm[-n:] == new_norm[:n]:
            best_overlap = n
            break
    return " ".join(new_words_raw[best_overlap:]).strip()


def _decode_mp3_to_pcm(path: str, sr: int) -> np.ndarray:
    """Decode an MP3 file to float32 mono PCM at the given sample rate.

    Uses PyAV (installed as a dependency of faster-whisper) so we don't need
    to shell out to ffmpeg.
    """
    import av  # ships with faster-whisper

    container = av.open(path)
    stream = next(s for s in container.streams if s.type == "audio")
    resampler = av.audio.resampler.AudioResampler(
        format="flt", layout="mono", rate=sr
    )
    chunks: list[np.ndarray] = []
    for frame in container.decode(stream):
        for resampled in resampler.resample(frame):
            arr = resampled.to_ndarray()  # shape (1, N) for mono
            chunks.append(arr.reshape(-1))
    # Flush resampler
    for resampled in resampler.resample(None) or []:
        arr = resampled.to_ndarray()
        chunks.append(arr.reshape(-1))
    container.close()
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32)


def _lang_name(code: str) -> str:
    table = {
        "en": "English", "en-US": "English", "en-GB": "English",
        "es": "Spanish", "es-US": "Spanish", "es-ES": "Spanish", "es-MX": "Spanish",
        "zh": "Chinese (Mandarin)", "zh-CN": "Chinese (Mandarin)",
        "ar": "Arabic", "ar-SA": "Arabic",
        "uk": "Ukrainian", "uk-UA": "Ukrainian",
        "ru": "Russian", "ru-RU": "Russian",
        "vi": "Vietnamese", "vi-VN": "Vietnamese",
        "fr": "French", "fr-FR": "French",
        "de": "German", "de-DE": "German",
        "pt": "Portuguese", "pt-BR": "Portuguese",
        "pl": "Polish",
        "hi": "Hindi",
        "ja": "Japanese",
        "ko": "Korean",
        "tl": "Tagalog",
        "it": "Italian",
    }
    return table.get(code, table.get(code.split("-")[0], code))


# ─── WebSocket route ──────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    call_id = uuid.uuid4().hex[:8]
    session = CallSession(ws, call_id)
    log.info("[%s] client connected", call_id)

    # Send scenarios list + active LLM info immediately so the UI can render
    # the demo picker and the backend badge.
    await session.send({"type": "scenarios_list", "scenarios": scenarios_summary()})
    backend = get_llm()
    await session.send(
        {
            "type": "llm_info",
            "backend": backend.name if backend else None,
            "model": backend.model if backend else None,
            "mode": "live" if backend else "local_rules",
        }
    )

    try:
        while True:
            msg = await ws.receive()
            if "text" in msg and msg["text"] is not None:
                await _handle_text(session, msg["text"])
            elif "bytes" in msg and msg["bytes"] is not None:
                # Binary = raw PCM16 mono @ 16kHz from live mic
                if not session.started:
                    continue
                if session.input_mode == "live_text":
                    session.input_mode = "live_audio"
                    session._start_audio_processor()
                pcm16 = np.frombuffer(msg["bytes"], dtype=np.int16)
                pcm = pcm16.astype(np.float32) / 32768.0
                try:
                    session._audio_queue.put_nowait(pcm)
                except asyncio.QueueFull:
                    log.debug("[%s] audio queue full, dropping chunk", session.call_id)
            elif msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        log.info("[%s] client disconnected", call_id)
    except Exception as e:
        log.exception("[%s] error: %s", call_id, e)
    finally:
        try:
            await session.stop()
        except Exception:
            pass


async def _handle_text(session: CallSession, raw: str):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await session.send({"type": "error", "message": "invalid json"})
        return
    t = data.get("type")

    if t == "start_call":
        session._reset_call_state()
        session.started = True
        session.input_mode = data.get("input_mode") or "live_text"
        if session.input_mode == "live_audio":
            session._start_audio_processor()
        await session.send(
            {
                "type": "call_started",
                "call_id": session.call_id,
                "scenario_id": data.get("scenario_id"),
            }
        )

    elif t == "stop_call":
        session._reset_call_state()
        await session.send({"type": "call_ended"})

    elif t == "play_scenario":
        scen_id = data.get("scenario_id")
        if not scen_id:
            await session.send({"type": "error", "message": "scenario_id required"})
            return
        # Reset then play
        session._reset_call_state()
        session.started = True
        session.input_mode = "scenario"
        session.scenario_id = scen_id
        await session.send(
            {"type": "call_started", "call_id": session.call_id, "scenario_id": scen_id}
        )
        session._scenario_task = asyncio.create_task(session.play_scenario(scen_id))

    elif t == "manual_edit":
        field = data.get("field")
        value = data.get("value")
        if field:
            session.manual_edits.add(field)
            session.form_state[field] = value
            session.ai_filled_fields.discard(field)
            await session.send(
                {
                    "type": "form_update",
                    "fields": {field: value},
                    "ai_filled_fields": sorted(session.ai_filled_fields),
                }
            )

    elif t == "tts_request":
        text = data.get("text")
        lang = data.get("language", "en-US")
        translate = bool(data.get("translate", False))
        if not text:
            await session.send({"type": "error", "message": "text required"})
            return
        spoken_text = text
        if translate and session.llm is not None and not lang.lower().startswith("en"):
            try:
                spoken_text = await session.llm.translate_text(
                    _lang_name(lang), text, source_language="English"
                )
            except Exception as e:
                log.warning("custom TTS translation failed: %s", e)
        try:
            audio = await session.tts.synthesize(spoken_text, lang)
        except Exception as e:
            await session.send({"type": "error", "message": f"tts failed: {e}"})
            return
        await session.send(
            {
                "type": "tts_audio",
                "language": lang,
                "text": spoken_text,
                "audio_base64": base64.b64encode(audio).decode(),
            }
        )

    elif t == "live_transcript":
        if not session.started:
            return
        text = (data.get("text") or "").strip()
        is_final = bool(data.get("is_final", True))
        if not text:
            return

        session.last_audio_time = time.monotonic()

        if is_final:
            new_text = _merge_incremental(session.full_transcript, text)
            if new_text.strip():
                t_now = time.monotonic()
                session.final_segments.append(
                    TranscriptSegment(text=new_text, start=t_now, end=t_now, is_final=True)
                )
            session.provisional_segment = None
            await session.send({
                "type": "transcript_update",
                "segments": [s.model_dump() for s in session.final_segments[-5:]],
                "full_text": session.full_transcript,
                "interim_text": None,
                "operator_text": session.operator_transcript,
                "operator_interim_text": None,
                "language": session.language,
            })
            session._schedule_translation()
            session._schedule_claude(forced=True)
        else:
            interim_text = _merge_incremental(session.full_transcript, text) or text
            session.provisional_segment = TranscriptSegment(
                text=interim_text,
                start=time.monotonic(),
                end=time.monotonic(),
                is_final=False,
            )
            display = session.final_segments[-4:] + [session.provisional_segment]
            await session.send({
                "type": "transcript_update",
                "segments": [s.model_dump() for s in display],
                "full_text": session.full_transcript,
                "interim_text": session.interim_text,
                "operator_text": session.operator_transcript,
                "operator_interim_text": session.operator_interim_text,
                "language": session.language,
            })
            session._schedule_translation()
            session._schedule_claude()

    elif t == "list_scenarios":
        await session.send(
            {"type": "scenarios_list", "scenarios": scenarios_summary()}
        )

    else:
        await session.send({"type": "error", "message": f"unknown type: {t}"})


# ─── startup hook ─────────────────────────────────────────────────────────


@app.on_event("startup")
async def warmup():
    transcriber = get_transcriber()
    log.info("Warming up transcriber: %s…", transcriber.name)
    try:
        await transcriber.warmup()
    except Exception as e:
        log.warning("Transcriber warm-up skipped: %s", e)
    log.info("Ready.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
