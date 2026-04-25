import { useCallback, useReducer } from "react";
import type {
  FormFields,
  ScenarioSummary,
  ServerMessage,
  Suggestion,
} from "../types/dispatch";

export interface CallState {
  connected: boolean;
  inCall: boolean;
  callId: string | null;
  scenarios: ScenarioSummary[];
  scenarioId: string | null;
  scenarioTitle: string | null;
  playbackAudioUrl: string | null;
  transcript: string;
  transcriptInterim: string;
  operatorTranscript: string;
  operatorTranscriptInterim: string;
  transcriptSegments: { text: string; start: number; end: number }[];
  form: FormFields;
  aiFilledFields: Set<string>;
  manualEdits: Set<string>;
  suggestions: Suggestion[];
  dismissedSuggestionIds: Set<string>;
  priority: FormFields["priority"];
  priorityReasoning: string | null;
  highlights: string[];
  callerLanguage: string | null;
  callerLanguageName: string | null;
  translatedPhrases: { en: string; translated: string }[];
  // TTS events surfaced to the panel
  lastTTSAudio: { language: string; text: string; audio_base64: string } | null;
  errorMessage: string | null;
  llmBackend: string | null;
  llmModel: string | null;
  llmMode: "live" | "local_rules" | null;
}

export const INITIAL_STATE: CallState = {
  connected: false,
  inCall: false,
  callId: null,
  scenarios: [],
  scenarioId: null,
  scenarioTitle: null,
  playbackAudioUrl: null,
  transcript: "",
  transcriptInterim: "",
  operatorTranscript: "",
  operatorTranscriptInterim: "",
  transcriptSegments: [],
  form: {},
  aiFilledFields: new Set(),
  manualEdits: new Set(),
  suggestions: [],
  dismissedSuggestionIds: new Set(),
  priority: null,
  priorityReasoning: null,
  highlights: [],
  callerLanguage: null,
  callerLanguageName: null,
  translatedPhrases: [],
  lastTTSAudio: null,
  errorMessage: null,
  llmBackend: null,
  llmModel: null,
  llmMode: null,
};

type Action =
  | { kind: "server"; msg: ServerMessage }
  | { kind: "connected"; connected: boolean }
  | { kind: "reset" }
  | { kind: "manual_edit"; field: keyof FormFields; value: unknown }
  | { kind: "dismiss_suggestion"; id: string }
  | { kind: "clear_error" };

function reducer(state: CallState, action: Action): CallState {
  switch (action.kind) {
    case "connected":
      return { ...state, connected: action.connected };
    case "reset":
      return {
        ...INITIAL_STATE,
        connected: state.connected,
        scenarios: state.scenarios,
        dismissedSuggestionIds: new Set(),
      };
    case "manual_edit": {
      const manualEdits = new Set(state.manualEdits);
      manualEdits.add(action.field);
      const aiFilledFields = new Set(state.aiFilledFields);
      aiFilledFields.delete(action.field);
      return {
        ...state,
        manualEdits,
        aiFilledFields,
        form: { ...state.form, [action.field]: action.value as never },
      };
    }
    case "dismiss_suggestion": {
      const dismissedSuggestionIds = new Set(state.dismissedSuggestionIds);
      dismissedSuggestionIds.add(action.id);
      return {
        ...state,
        dismissedSuggestionIds,
        suggestions: state.suggestions.filter((s) => s.id !== action.id),
      };
    }
    case "clear_error":
      return { ...state, errorMessage: null };
    case "server": {
      const m = action.msg;
      switch (m.type) {
        case "scenarios_list":
          return { ...state, scenarios: m.scenarios };
        case "llm_info":
          return {
            ...state,
            llmBackend: m.backend,
            llmModel: m.model,
            llmMode: m.mode,
          };
        case "call_started":
          return {
            ...INITIAL_STATE,
            connected: state.connected,
            scenarios: state.scenarios,
            llmBackend: state.llmBackend,
            llmModel: state.llmModel,
            llmMode: state.llmMode,
            dismissedSuggestionIds: new Set(),
            inCall: true,
            callId: m.call_id,
            scenarioId: m.scenario_id ?? null,
          };
        case "call_ended":
          return {
            ...INITIAL_STATE,
            connected: state.connected,
            scenarios: state.scenarios,
            llmBackend: state.llmBackend,
            llmModel: state.llmModel,
            llmMode: state.llmMode,
            dismissedSuggestionIds: new Set(),
          };
        case "scenario_playback":
          return {
            ...state,
            scenarioId: m.scenario_id,
            playbackAudioUrl: m.audio_url,
            scenarioTitle: m.title,
          };
        case "scenario_finished":
          return state;
        case "transcript_update":
          return {
            ...state,
            transcript: m.full_text,
            transcriptInterim: m.interim_text ?? "",
            operatorTranscript: m.operator_text ?? m.full_text,
            operatorTranscriptInterim: m.operator_interim_text ?? m.interim_text ?? "",
            transcriptSegments: m.segments.map((s) => ({
              text: s.text,
              start: s.start,
              end: s.end,
            })),
          };
        case "form_update": {
          const form = { ...state.form, ...(m.fields as FormFields) };
          return {
            ...state,
            form,
            aiFilledFields: new Set([
              ...m.ai_filled_fields,
              ...Array.from(state.aiFilledFields),
            ].filter((f) => !state.manualEdits.has(f))),
          };
        }
        case "suggestions":
          return {
            ...state,
            suggestions: m.suggestions.filter(
              (s) => !state.dismissedSuggestionIds.has(s.id)
            ),
          };
        case "priority_update":
          return {
            ...state,
            priority: m.priority,
            priorityReasoning: m.reasoning ?? null,
          };
        case "highlights":
          return { ...state, highlights: m.keywords };
        case "language_detected":
          return {
            ...state,
            callerLanguage: m.language,
            callerLanguageName: m.language_name,
          };
        case "phrases_ready":
          return { ...state, translatedPhrases: m.phrases };
        case "tts_audio":
          return {
            ...state,
            lastTTSAudio: {
              language: m.language,
              text: m.text,
              audio_base64: m.audio_base64,
            },
          };
        case "error":
          return { ...state, errorMessage: m.message };
      }
    }
  }
}

export function useCallState() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const onServerMessage = useCallback((msg: ServerMessage) => {
    dispatch({ kind: "server", msg });
  }, []);

  const setConnected = useCallback((connected: boolean) => {
    dispatch({ kind: "connected", connected });
  }, []);

  const editField = useCallback((field: keyof FormFields, value: unknown) => {
    dispatch({ kind: "manual_edit", field, value });
  }, []);

  const dismissSuggestion = useCallback((id: string) => {
    dispatch({ kind: "dismiss_suggestion", id });
  }, []);

  const reset = useCallback(() => dispatch({ kind: "reset" }), []);
  const clearError = useCallback(() => dispatch({ kind: "clear_error" }), []);

  return {
    state,
    onServerMessage,
    setConnected,
    editField,
    dismissSuggestion,
    reset,
    clearError,
  };
}
