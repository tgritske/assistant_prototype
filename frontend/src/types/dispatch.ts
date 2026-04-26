import { z } from "zod";

export const FormFieldsSchema = z.object({
  incident_type: z.enum(["medical", "fire", "police", "traffic", "other"]).nullable().optional(),
  priority: z.enum(["P1", "P2", "P3", "P4"]).nullable().optional(),
  caller_name: z.string().nullable().optional(),
  callback_number: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  cross_street: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  injuries_reported: z.enum(["yes", "no", "unknown"]).nullable().optional(),
  num_victims: z.number().int().nullable().optional(),
  victim_age: z.string().nullable().optional(),
  victim_condition: z.string().nullable().optional(),
  hazards: z.string().nullable().optional(),
  weapons_involved: z.enum(["yes", "no", "unknown"]).nullable().optional(),
  suspect_description: z.string().nullable().optional(),
  vehicle_info: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});

export type FormFields = z.infer<typeof FormFieldsSchema>;

export const SuggestionSchema = z.object({
  id: z.string(),
  trigger: z.string(),
  question: z.string(),
  urgency: z.enum(["high", "medium", "low"]).default("medium"),
  rationale: z.string().optional().nullable(),
  category: z.enum(["safety", "pre_arrival", "medical", "info"]).optional().nullable(),
  suggestion_type: z.enum(["ask", "instruct"]).default("ask"),
});

export type Suggestion = z.infer<typeof SuggestionSchema>;

export const TranscriptSegmentSchema = z.object({
  text: z.string(),
  start: z.number(),
  end: z.number(),
  is_final: z.boolean().default(true),
});

export type TranscriptSegment = z.infer<typeof TranscriptSegmentSchema>;

export const SpeakerSchema = z.enum(["caller", "worker"]);
export type Speaker = z.infer<typeof SpeakerSchema>;

export const DialogueTurnSchema = z.object({
  id: z.string(),
  seq: z.number().int(),
  speaker: SpeakerSchema,
  channel: z.string(),
  source: z.enum(["whisper", "web_speech", "typed", "tts_request", "demo"]),
  text: z.string(),
  text_en: z.string().nullable().optional(),
  start: z.number(),
  end: z.number(),
  is_final: z.boolean().default(true),
  language: z.string().nullable().optional(),
  confidence: z.number().nullable().optional(),
});

export type DialogueTurn = z.infer<typeof DialogueTurnSchema>;

export const ScenarioSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  category: z.string(),
  language: z.string(),
  difficulty: z.string(),
});

export type ScenarioSummary = z.infer<typeof ScenarioSummarySchema>;

// ─── Server → Client message envelopes ──

export const ServerMessageSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("scenarios_list"),
    scenarios: z.array(ScenarioSummarySchema),
  }),
  z.object({
    type: z.literal("llm_info"),
    backend: z.string().nullable(),
    model: z.string().nullable(),
    mode: z.enum(["live", "local_rules"]),
  }),
  z.object({
    type: z.literal("call_started"),
    call_id: z.string(),
    scenario_id: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("call_ended"),
  }),
  z.object({
    type: z.literal("scenario_playback"),
    scenario_id: z.string(),
    audio_url: z.string(),
    language: z.string(),
    title: z.string(),
  }),
  z.object({
    type: z.literal("scenario_finished"),
    scenario_id: z.string(),
  }),
  z.object({
    type: z.literal("transcript_update"),
    segments: z.array(TranscriptSegmentSchema),
    full_text: z.string(),
    interim_text: z.string().nullable().optional(),
    operator_text: z.string().nullable().optional(),
    operator_interim_text: z.string().nullable().optional(),
    language: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("dialogue_update"),
    turns: z.array(DialogueTurnSchema),
    caller_text: z.string(),
    caller_interim_text: z.string().nullable().optional(),
    caller_interim_text_en: z.string().nullable().optional(),
    worker_text: z.string(),
    worker_interim_text: z.string().nullable().optional(),
    full_text: z.string(),
    language: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("form_update"),
    fields: z.record(z.string(), z.any()),
    ai_filled_fields: z.array(z.string()),
  }),
  z.object({
    type: z.literal("suggestions"),
    suggestions: z.array(SuggestionSchema),
  }),
  z.object({
    type: z.literal("priority_update"),
    priority: z.enum(["P1", "P2", "P3", "P4"]),
    reasoning: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("highlights"),
    keywords: z.array(z.string()),
  }),
  z.object({
    type: z.literal("language_detected"),
    language: z.string(),
    language_name: z.string(),
  }),
  z.object({
    type: z.literal("phrases_ready"),
    language: z.string(),
    phrases: z.array(z.object({ en: z.string(), translated: z.string() })),
  }),
  z.object({
    type: z.literal("tts_audio"),
    language: z.string(),
    text: z.string(),
    audio_base64: z.string(),
  }),
  z.object({
    type: z.literal("error"),
    message: z.string(),
  }),
]);

export type ServerMessage = z.infer<typeof ServerMessageSchema>;
