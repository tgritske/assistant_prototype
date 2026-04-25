from __future__ import annotations

import re
from typing import Optional

from schemas import ClaudeExtraction, FormFields, Suggestion
from services.form_normalizer import extract_address


PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{8,}\d)")
EN_AGE_RE = re.compile(r"\b(\d{1,3})\s*(?:years? old|yo)\b", re.IGNORECASE)
COUNT_RE = re.compile(
    r"\b(\d{1,2})\s*(?:victims?|people|injured|children|kids)\b",
    re.IGNORECASE,
)
EN_NAME_RE = re.compile(
    r"(?:my name is|this is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    re.IGNORECASE,
)
FIRE_OCCUPANCY_RE = re.compile(
    r"\b(?:i think|maybe|possibly|probably)\s+((?:(?:mr|mrs|ms|miss)\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:might|may|could|is)?\s*(?:still\s+)?(?:be\s+)?inside\b",
    re.IGNORECASE,
)
FIRE_NEIGHBOR_LOCATION_RE = re.compile(
    r"\b(?:i(?:'m| am)\s+(?:at|on)|my house is(?:\s+at)?)\s+(\d{1,6}[A-Za-z0-9-]*)\b",
    re.IGNORECASE,
)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
}


def extract_realtime_signal(
    transcript: str,
    existing_form: Optional[dict] = None,
) -> ClaudeExtraction:
    """Fast local extraction pass used for live UI updates.

    This layer intentionally uses only evidence present in the current
    transcript. It provides low-latency classification, form hints, and
    suggestions while slower model-based refinement catches up.
    """
    text = (transcript or "").strip()
    if not text:
        return ClaudeExtraction()

    norm = text.lower()
    form = (existing_form or {}).copy()

    incident_type = _detect_incident_type(norm)
    priority = _detect_priority(norm, incident_type)
    injuries = _detect_injuries(norm)
    weapons = _detect_weapons(norm)
    num_victims = _extract_num_victims(text)
    age = _extract_age(text)
    caller_name = _extract_name(text)
    callback = _extract_phone(text)
    location = _extract_location(text)
    condition = _detect_condition(norm)
    hazards = _detect_hazards(norm)
    vehicle_info = _extract_vehicle_info(text, norm)
    suspect_description = _extract_suspect_description(text, norm)
    notes = _extract_notes(text, norm, incident_type)

    description = _build_description(incident_type, norm)
    priority_reasoning = _priority_reasoning(priority, incident_type)
    suggestions = _build_suggestions(
        norm=norm,
        incident_type=incident_type,
        priority=priority,
        location=location or form.get("location"),
        callback=callback or form.get("callback_number"),
        weapons=weapons,
    )
    highlights = _build_highlights(text, norm, incident_type)

    fields = FormFields(
        incident_type=incident_type,
        priority=priority,
        caller_name=caller_name,
        callback_number=callback,
        location=location,
        cross_street=None,
        description=description,
        injuries_reported=injuries,
        num_victims=num_victims,
        victim_age=age,
        victim_condition=condition,
        hazards=hazards,
        weapons_involved=weapons,
        suspect_description=suspect_description,
        vehicle_info=vehicle_info,
        notes=notes,
    )

    return ClaudeExtraction(
        form_fields=fields,
        suggestions=suggestions[:4],
        highlight_keywords=highlights[:10],
        priority_reasoning=priority_reasoning,
    )


def _detect_incident_type(norm: str) -> Optional[str]:
    categories = {
        "medical": [
            "breath", "unconscious", "chest pain", "heart", "stroke", "overdose", "seizure",
        ],
        "fire": [
            "fire", "smoke", "flames", "gas leak", "carbon monoxide",
        ],
        "police": [
            "knife", "gun", "weapon", "assault", "fight", "threat", "break in", "robbery",
        ],
        "traffic": [
            "crash", "accident", "car", "vehicle", "collision", "hit by",
        ],
    }
    best: Optional[str] = None
    best_score = 0
    for category, phrases in categories.items():
        score = sum(1 for phrase in phrases if phrase in norm)
        if score > best_score:
            best = category
            best_score = score
    return best or "other"


def _detect_priority(norm: str, incident_type: Optional[str]) -> Optional[str]:
    p1 = [
        "not breathing", "unconscious", "cardiac arrest", "severe bleeding", "fire", "gun", "knife",
    ]
    p2 = [
        "overdose", "chest pain", "domestic", "crash",
    ]
    p3 = [
        "minor", "property damage",
    ]
    if any(token in norm for token in p1):
        return "P1"
    if any(token in norm for token in p2):
        return "P2"
    if incident_type in {"medical", "fire", "police", "traffic"}:
        return "P3"
    if any(token in norm for token in p3):
        return "P3"
    return "P4"


def _detect_injuries(norm: str) -> Optional[str]:
    if any(token in norm for token in ["hurt", "injur", "bleed", "burn"]):
        return "yes"
    if any(token in norm for token in ["no injuries", "not hurt"]):
        return "no"
    return "unknown"


def _detect_weapons(norm: str) -> Optional[str]:
    if any(token in norm for token in ["gun", "knife", "weapon"]):
        return "yes"
    return "unknown"


def _extract_num_victims(text: str) -> Optional[int]:
    match = COUNT_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None

    lowered = text.lower()
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b\s+(?:children|kids|people|victims)", lowered):
            return value
    return None


def _extract_age(text: str) -> Optional[str]:
    match = EN_AGE_RE.search(text)
    return match.group(1) if match else None


def _extract_name(text: str) -> Optional[str]:
    match = EN_NAME_RE.search(text)
    if not match:
        return None
    name = " ".join(part.capitalize() for part in match.group(1).split())
    return name.strip() or None


def _extract_phone(text: str) -> Optional[str]:
    match = PHONE_RE.search(text)
    if not match:
        return None
    number = re.sub(r"[^\d+]", "", match.group(0))
    return number if len(re.sub(r"\D", "", number)) >= 9 else None


def _extract_location(text: str) -> Optional[str]:
    return extract_address(text)


def _detect_condition(norm: str) -> Optional[str]:
    condition_map = [
        (["not breathing"], "Not breathing"),
        (["unconscious"], "Unconscious"),
        (["barely breathing", "trouble breathing"], "Trouble breathing"),
        (["bleeding heavily"], "Severe bleeding"),
        (["chest pain"], "Chest pain"),
    ]
    for needles, label in condition_map:
        if any(needle in norm for needle in needles):
            return label
    return None


def _detect_hazards(norm: str) -> Optional[str]:
    hazards: list[str] = []
    mapping = [
        (["gun", "knife", "weapon"], "Weapon on scene"),
        (["fire", "smoke"], "Fire / smoke"),
        (["gas leak"], "Gas leak"),
        (["vehicle", "car", "fuel"], "Vehicle / possible fuel hazard"),
        (["children", "kids", "cries", "crying"], "Possible occupants inside"),
    ]
    for needles, label in mapping:
        if any(needle in norm for needle in needles):
            hazards.append(label)
    return ", ".join(dict.fromkeys(hazards)) or None


def _extract_vehicle_info(text: str, norm: str) -> Optional[str]:
    if "vehicle" not in norm and "car" not in norm:
        return None
    for sentence in re.split(r"[.!?]", text):
        lower = sentence.lower()
        if any(token in lower for token in ["car", "vehicle", "truck", "bus"]):
            return sentence.strip()[:120] or "Vehicle incident"
    return "Vehicle incident"


def _extract_suspect_description(text: str, norm: str) -> Optional[str]:
    if "police" not in (_detect_incident_type(norm) or "") and not any(
        token in norm for token in ["suspect", "attacker", "assault"]
    ):
        return None
    for sentence in re.split(r"[.!?]", text):
        lower = sentence.lower()
        if any(token in lower for token in ["suspect", "man", "woman", "red", "black", "shirt"]):
            return sentence.strip()[:160]
    return "Suspect on scene"


def _build_description(incident_type: Optional[str], norm: str) -> Optional[str]:
    descriptions = {
        "medical": "Medical emergency",
        "fire": "Fire / smoke emergency",
        "police": "Active police incident",
        "traffic": "Traffic collision",
        "other": "Emergency incident",
    }
    desc = descriptions.get(incident_type or "other")
    if incident_type == "medical":
        if "not breathing" in norm:
            return "Patient not breathing"
        if "chest pain" in norm:
            return "Chest pain, urgent medical response"
    if incident_type == "fire" and "gas" in norm:
        return "Gas leak / ignition risk"
    if incident_type == "fire" and any(token in norm for token in ["children", "kids", "cries"]):
        return "Fire with possible occupants inside"
    return desc


def _extract_notes(text: str, norm: str, incident_type: Optional[str]) -> Optional[str]:
    notes: list[str] = []

    if incident_type == "fire":
        floor_match = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+floor\b", text, re.IGNORECASE)
        if floor_match:
            notes.append(f"Reported on floor {floor_match.group(1)}")
        elif "third floor" in norm:
            notes.append("Reported on third floor")

        if any(token in norm for token in ["children", "kids"]):
            notes.append("Children may be inside")
        if any(token in norm for token in ["cries", "crying"]):
            notes.append("Caller heard cries from inside")
        if "orange flames" in norm:
            notes.append("Orange flames visible")
        if any(token in norm for token in ["black smoke", "thick smoke"]):
            notes.append("Heavy smoke visible")
        if any(token in norm for token in ["upstairs windows", "upper windows"]):
            notes.append("Flames visible from upper windows")
        if any(token in norm for token in ["cracking", "roof"]):
            notes.append("Possible roof involvement")
        occupant = _extract_possible_fire_occupant(text, norm)
        if occupant:
            notes.append(occupant)
        neighbor_location = _extract_neighbor_reference(text)
        if neighbor_location:
            notes.append(neighbor_location)

    return "; ".join(dict.fromkeys(notes)) or None


def _extract_possible_fire_occupant(text: str, norm: str) -> Optional[str]:
    match = FIRE_OCCUPANCY_RE.search(text)
    if match:
        stop_words = {"might", "may", "could", "is", "still", "be", "inside"}
        name_parts = [
            part for part in match.group(1).split()
            if part.lower().strip(".") not in stop_words
        ]
        name = " ".join(part[:1].upper() + part[1:] for part in name_parts)
        return f"Possible occupant inside: {name.strip()}"
    if any(token in norm for token in ["someone inside", "person inside"]):
        return "Possible occupant inside"
    return None


def _extract_neighbor_reference(text: str) -> Optional[str]:
    match = FIRE_NEIGHBOR_LOCATION_RE.search(text)
    if not match:
        return None
    return f"Caller reports they are at {match.group(1)}"


def _priority_reasoning(priority: Optional[str], incident_type: Optional[str]) -> Optional[str]:
    if priority == "P1":
        if incident_type == "medical":
            return "Immediate life-threatening medical signs"
        if incident_type == "fire":
            return "Active fire or gas leak"
        if incident_type == "police":
            return "Weapon or active violence on scene"
        return "Immediate life threat"
    if priority == "P2":
        return "Serious situation requiring urgent response"
    if priority == "P3":
        return "Urgent but not clearly life-threatening"
    return "Limited information / lower urgency"


def _build_suggestions(
    *,
    norm: str,
    incident_type: Optional[str],
    priority: Optional[str],
    location: Optional[str],
    callback: Optional[str],
    weapons: Optional[str],
) -> list[Suggestion]:
    suggestions: list[Suggestion] = []

    def add(id_: str, trigger: str, question: str, urgency: str, category: str, suggestion_type: str, rationale: Optional[str] = None):
        suggestions.append(
            Suggestion(
                id=id_,
                trigger=trigger,
                question=question,
                urgency=urgency,  # type: ignore[arg-type]
                category=category,  # type: ignore[arg-type]
                suggestion_type=suggestion_type,  # type: ignore[arg-type]
                rationale=rationale,
            )
        )

    if not location:
        add(
            "need_location",
            "location_missing",
            "What is the exact address?",
            "high",
            "info",
            "ask",
            "Dispatch needs an exact location",
        )
    if not callback:
        add(
            "need_callback",
            "callback_missing",
            "What callback number are you calling from?",
            "medium",
            "info",
            "ask",
        )

    if incident_type == "medical":
        if any(token in norm for token in ["not breathing", "unconscious"]):
            add(
                "medical_cpr",
                "critical_medical",
                "Tell the caller to start chest compressions immediately.",
                "high",
                "pre_arrival",
                "instruct",
            )
        else:
            add(
                "medical_breathing_check",
                "medical_status",
                "Is the patient breathing and conscious?",
                "high",
                "medical",
                "ask",
            )
    elif incident_type == "fire":
        add(
            "fire_evacuate",
            "fire_detected",
            "Tell the caller to evacuate immediately and not re-enter.",
            "high",
            "pre_arrival",
            "instruct",
        )
        add(
            "fire_occupants",
            "fire_detected",
            "Is everyone out of the building?",
            "high",
            "safety",
            "ask",
        )
    elif incident_type == "police":
        if weapons == "yes":
            add(
                "police_weapon",
                "weapon_detected",
                "Does the suspect still have the weapon in hand?",
                "high",
                "safety",
                "ask",
            )
        add(
            "police_safe_hide",
            "police_incident",
            "Tell the caller to stay hidden and avoid the suspect.",
            "high",
            "safety",
            "instruct",
        )
    elif incident_type == "traffic":
        add(
            "traffic_victims",
            "traffic_detected",
            "How many people are injured, and can anyone exit the vehicle?",
            "high",
            "info",
            "ask",
        )
        add(
            "traffic_hazard",
            "traffic_detected",
            "Is there smoke, fire, or a fuel leak?",
            "medium",
            "safety",
            "ask",
        )

    if priority == "P1" and incident_type not in {"medical", "fire", "police", "traffic"}:
        add(
            "scene_safe",
            "critical_incident",
            "Is the scene safe right now?",
            "high",
            "safety",
            "ask",
        )

    # Deduplicate while keeping order.
    deduped: list[Suggestion] = []
    seen: set[str] = set()
    for item in suggestions:
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return deduped


def _build_highlights(text: str, norm: str, incident_type: Optional[str]) -> list[str]:
    highlights: list[str] = []
    phrases = [
        "not breathing", "unconscious", "chest pain", "bleeding", "fire", "smoke", "gas leak", "knife", "gun", "accident",
    ]
    for phrase in phrases:
        if phrase in norm:
            highlights.append(phrase)
    location = _extract_location(text)
    phone = _extract_phone(text)
    age = _extract_age(text)
    if location:
        highlights.append(location)
    if phone:
        highlights.append(phone)
    if age:
        highlights.append(age)
    if incident_type:
        highlights.append(
            {
                "medical": "medical",
                "fire": "fire",
                "police": "police",
                "traffic": "traffic",
                "other": "emergency",
            }[incident_type]
        )
    seen: set[str] = set()
    unique: list[str] = []
    for item in highlights:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
