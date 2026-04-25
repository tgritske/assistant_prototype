from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


IncidentType = Literal["medical", "fire", "police", "traffic", "other"]
Priority = Literal["P1", "P2", "P3", "P4"]
YesNoUnknown = Literal["yes", "no", "unknown"]


class FormFields(BaseModel):
    incident_type: Optional[IncidentType] = None
    priority: Optional[Priority] = None
    caller_name: Optional[str] = None
    callback_number: Optional[str] = None
    location: Optional[str] = None
    cross_street: Optional[str] = None
    description: Optional[str] = None
    injuries_reported: Optional[YesNoUnknown] = None
    num_victims: Optional[int] = None
    victim_age: Optional[str] = None
    victim_condition: Optional[str] = None
    hazards: Optional[str] = None
    weapons_involved: Optional[YesNoUnknown] = None
    suspect_description: Optional[str] = None
    vehicle_info: Optional[str] = None
    notes: Optional[str] = None


SuggestionCategory = Literal["safety", "pre_arrival", "medical", "info"]
SuggestionType = Literal["ask", "instruct"]


class Suggestion(BaseModel):
    id: str
    trigger: str
    question: str
    urgency: Literal["high", "medium", "low"] = "medium"
    rationale: Optional[str] = None
    category: Optional[SuggestionCategory] = None
    suggestion_type: SuggestionType = "ask"


class ClaudeExtraction(BaseModel):
    form_fields: FormFields = Field(default_factory=FormFields)
    suggestions: list[Suggestion] = Field(default_factory=list)
    highlight_keywords: list[str] = Field(default_factory=list)
    priority_reasoning: Optional[str] = None
    detected_language: Optional[str] = None


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float
    is_final: bool = True


# ─── WebSocket message envelopes ─────────────────────────────────────────

class ClientStartCall(BaseModel):
    type: Literal["start_call"] = "start_call"
    scenario_id: Optional[str] = None
    sample_rate: int = 16000
    input_mode: Literal["live_text", "live_audio"] = "live_text"


class ClientAudioMeta(BaseModel):
    type: Literal["audio_meta"] = "audio_meta"
    mime: str
    sample_rate: int = 16000


class ClientStopCall(BaseModel):
    type: Literal["stop_call"] = "stop_call"


class ClientManualEdit(BaseModel):
    type: Literal["manual_edit"] = "manual_edit"
    field: str
    value: Optional[str] = None


class ClientTTSRequest(BaseModel):
    type: Literal["tts_request"] = "tts_request"
    text: str
    language: str = "en-US"
    translate: bool = False


class ClientListScenarios(BaseModel):
    type: Literal["list_scenarios"] = "list_scenarios"


class ClientPlayScenario(BaseModel):
    type: Literal["play_scenario"] = "play_scenario"
    scenario_id: str


# Server → Client

class ServerTranscriptUpdate(BaseModel):
    type: Literal["transcript_update"] = "transcript_update"
    segments: list[TranscriptSegment]
    full_text: str
    interim_text: Optional[str] = None
    operator_text: Optional[str] = None
    operator_interim_text: Optional[str] = None
    language: Optional[str] = None


class ServerFormUpdate(BaseModel):
    type: Literal["form_update"] = "form_update"
    fields: dict
    ai_filled_fields: list[str]


class ServerSuggestions(BaseModel):
    type: Literal["suggestions"] = "suggestions"
    suggestions: list[Suggestion]


class ServerPriorityUpdate(BaseModel):
    type: Literal["priority_update"] = "priority_update"
    priority: Priority
    reasoning: Optional[str] = None


class ServerHighlights(BaseModel):
    type: Literal["highlights"] = "highlights"
    keywords: list[str]


class ServerLanguageDetected(BaseModel):
    type: Literal["language_detected"] = "language_detected"
    language: str
    language_name: str


class ServerCallStarted(BaseModel):
    type: Literal["call_started"] = "call_started"
    call_id: str
    scenario_id: Optional[str] = None


class ServerCallEnded(BaseModel):
    type: Literal["call_ended"] = "call_ended"


class ServerScenariosList(BaseModel):
    type: Literal["scenarios_list"] = "scenarios_list"
    scenarios: list[dict]


class ServerError(BaseModel):
    type: Literal["error"] = "error"
    message: str
