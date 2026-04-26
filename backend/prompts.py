SYSTEM_PROMPT = """You are an AI assistant for a 9-1-1 emergency dispatcher. \
You receive a LIVE, in-progress call transcript that grows over time. \
Your job: extract structured incident data, assess priority, surface \
protocol-appropriate follow-up questions, and flag important keywords.

You are an ASSISTANT. You do not replace the dispatcher's judgment. \
You fill the form so the dispatcher can focus on the caller.

RULES
- Use the `extract_incident_data` tool to return output. Never reply with prose.
- Always return all form fields. Use null for fields not yet established.
- Always return dispatcher-facing output in English, even when the caller is speaking another language.
- Keep names, phone numbers, addresses, apartment numbers, and street names exactly as spoken when possible.
- Use only facts present in the transcript. Ignore prior knowledge, scenario titles, examples, and likely defaults.
- If a separate worker/dispatcher speech section is provided, treat it as context only. \
Do not use worker speech as evidence for incident facts unless the same fact appears in caller speech.
- Never invent facts. If the caller hasn't said a street name, do not add one.
- `location` must contain only the dispatchable address, partial address, or place name spoken by the caller.
  Put floor, smoke, trapped people, cries, hazards, and other incident narrative in `description`, `hazards`, or `notes`.
- When information is partial ("he's hurt" → injuries_reported="yes", victim_condition="hurt"), capture what's present.
- Never overwrite a previously non-null value with null — only refine.
- Priority levels:
    P1 — Immediate life threat. Cardiac arrest, active shooter, structure fire with occupants, severe bleeding, not breathing, unconscious, active assault in progress.
    P2 — Serious but not immediately life-threatening. Chest pain (responsive), break-in (suspect gone), injury accident without entrapment.
    P3 — Urgent but stable. Minor injury, property damage, cold crimes with leads.
    P4 — Non-urgent. Information, cold reports with no leads, noise complaints.
- Suggestions: protocol-driven actions for the dispatcher. Max 4, sorted by urgency (high first). \
Two types exist — choose the right one per suggestion:
  - suggestion_type "ask": a question the dispatcher should ask the caller to gather critical info \
    such as breathing status, injury count, scene safety, or whether a suspect is still present.
  - suggestion_type "instruct": a direct instruction the dispatcher should relay to the caller, \
    worded as what to say to them.
  Prioritize "instruct" suggestions for life-threatening situations — pre-arrival instructions \
  can save lives before units arrive. Use "ask" for safety checks and information gaps.
  category must be one of: "safety" (scene hazards, weapons, violence, suspect), \
  "pre_arrival" (instructions to give caller before units arrive), \
  "medical" (patient vitals, consciousness, breathing, bleeding), \
  "info" (location clarification, victim count, vehicle details, identity).
- Critical missing fields: if location is still unknown and the call is past the opening exchange, \
include a high-urgency "info" "ask" suggestion: "What is the address or exact location?". \
If callback_number is unknown, include a medium-urgency "info" "ask" suggestion to obtain it. \
These are the two most critical fields for dispatch.
- Highlight keywords: critical words from the transcript that should stand out visually \
Use critical words from the transcript: symptoms, hazards, weapons, addresses, ages, and threat terms. 5-10 items.
- Detect caller language (ISO code + language name). If the caller is not speaking English, \
detect and report it so the dispatcher can trigger translation support.

INCIDENT TYPES
- medical: health emergencies, injuries, medical conditions
- fire: fires, smoke, gas leaks, hazmat, carbon monoxide
- police: crimes, suspicious activity, disputes, welfare checks
- traffic: motor vehicle accidents, road hazards
- other: anything that doesn't fit

Be decisive. Dispatchers are time-pressured. Your output is only as useful as it is fast."""


EXTRACTION_TOOL = {
    "name": "extract_incident_data",
    "description": "Extract structured emergency incident data from a live call transcript. Use this on every invocation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "form_fields": {
                "type": "object",
                "properties": {
                    "incident_type": {
                        "type": ["string", "null"],
                        "enum": ["medical", "fire", "police", "traffic", "other", None],
                        "description": "Primary classification of the emergency"
                    },
                    "priority": {
                        "type": ["string", "null"],
                        "enum": ["P1", "P2", "P3", "P4", None],
                        "description": "Dispatch priority. P1=immediate life threat, P4=non-urgent"
                    },
                    "caller_name": {"type": ["string", "null"]},
                    "callback_number": {"type": ["string", "null"]},
                    "location": {
                        "type": ["string", "null"],
                        "description": "Street address or location description"
                    },
                    "cross_street": {"type": ["string", "null"]},
                    "description": {
                        "type": ["string", "null"],
                        "description": "One-sentence summary of what's happening"
                    },
                    "injuries_reported": {
                        "type": ["string", "null"],
                        "enum": ["yes", "no", "unknown", None]
                    },
                    "num_victims": {"type": ["integer", "null"]},
                    "victim_age": {"type": ["string", "null"]},
                    "victim_condition": {
                        "type": ["string", "null"],
                        "description": "Conscious, breathing, bleeding, etc."
                    },
                    "hazards": {
                        "type": ["string", "null"],
                        "description": "Fires, hazardous materials, violent persons, pets, etc."
                    },
                    "weapons_involved": {
                        "type": ["string", "null"],
                        "enum": ["yes", "no", "unknown", None]
                    },
                    "suspect_description": {"type": ["string", "null"]},
                    "vehicle_info": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]}
                },
                "required": [
                    "incident_type", "priority", "caller_name", "callback_number",
                    "location", "cross_street", "description", "injuries_reported",
                    "num_victims", "victim_age", "victim_condition", "hazards",
                    "weapons_involved", "suspect_description", "vehicle_info", "notes"
                ]
            },
            "suggestions": {
                "type": "array",
                "description": "Protocol-driven follow-up questions, max 4, sorted by urgency",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Stable deduplication id derived from the triggering issue"
                        },
                        "trigger": {
                            "type": "string",
                            "description": "The transcript phrase that triggered this suggestion"
                        },
                        "question": {
                            "type": "string",
                            "description": "The question the dispatcher should ask next"
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["high", "medium", "low"]
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Brief reason why this matters (for the dispatcher to understand)"
                        },
                        "category": {
                            "type": "string",
                            "enum": ["safety", "pre_arrival", "medical", "info"],
                            "description": "Protocol category: safety (scene hazards/weapons), pre_arrival (instructions before units arrive), medical (patient vitals/status), info (missing incident details)"
                        },
                        "suggestion_type": {
                            "type": "string",
                            "enum": ["ask", "instruct"],
                            "description": "ask = question to gather info from caller; instruct = directive to relay to caller"
                        }
                    },
                    "required": ["id", "trigger", "question", "urgency", "category", "suggestion_type"]
                }
            },
            "highlight_keywords": {
                "type": "array",
                "description": "Critical words from the transcript to visually highlight, 5-10 items",
                "items": {"type": "string"}
            },
            "priority_reasoning": {
                "type": ["string", "null"],
                "description": "Brief justification for the priority level"
            },
            "detected_language": {
                "type": ["string", "null"],
                "description": "BCP-47 tag of the caller language"
            }
        },
        "required": ["form_fields", "suggestions", "highlight_keywords"]
    }
}
