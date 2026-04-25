from __future__ import annotations

import re
from typing import Any, Optional

from schemas import ClaudeExtraction, FormFields, Suggestion


CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
PHONE_DIGITS_RE = re.compile(r"\D+")
WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

EN_STREET_TYPES = (
    "street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
    "drive", "dr", "lane", "ln", "way", "place", "pl", "court", "ct",
)
EN_STREET_TYPE_RE = "|".join(re.escape(item) for item in EN_STREET_TYPES)

EN_ADDRESS_PATTERNS = [
    re.compile(
        rf"\b(?:at|on|near|address(?:\s+is)?|location(?:\s+is)?|located\s+at)\s+((?:[A-Za-z][A-Za-z'.-]*\s+){{0,4}}(?:{EN_STREET_TYPE_RE})\.?\s+\d+[A-Za-z0-9-]*)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b((?:[A-Z][A-Za-z'.-]*\s+){{1,4}}(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Way|Place|Pl\.?|Court|Ct\.?)\s+\d+[A-Za-z0-9-]*)\b",
    ),
    re.compile(
        rf"\b(?:at|on|near|address(?:\s+is)?|location(?:\s+is)?|located\s+at)\s+(\d+[A-Za-z0-9-]*\s+(?:[A-Za-z][A-Za-z'.-]*\s+){{1,4}}(?:{EN_STREET_TYPE_RE})\.?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:address(?:\s+is)?|location(?:\s+is)?|located\s+at)\s+(\d+[A-Za-z0-9-]*)[\s,.;:-]+((?:[A-Za-z][A-Za-z'.-]*\s+){{1,4}}(?:{EN_STREET_TYPE_RE})\.?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:at|on|near|address(?:\s+is)?|location(?:\s+is)?|located\s+at)\s+(\d{1,6}[A-Za-z0-9-]*)\b",
        re.IGNORECASE,
    ),
]

RU_ADDRESS_PATTERNS = [
    re.compile(
        r"(?:\b|\s)(улиц[а-яё]*|ул\.?|проспект[а-яё]*|пр-т|переулок[а-яё]*|проезд[а-яё]*|шоссе|площад[а-яё]*)\s+([А-Яа-яЁёA-Za-z' .-]{2,50})\s+(\d+[А-Яа-яA-Za-z0-9-]*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:адрес|по адресу)\s+([А-Яа-яЁёA-Za-z' .-]{2,50})\s+(\d+[А-Яа-яA-Za-z0-9-]*)",
        re.IGNORECASE,
    ),
]

TEXT_FIELDS = {
    "caller_name",
    "location",
    "cross_street",
    "description",
    "victim_age",
    "victim_condition",
    "hazards",
    "suspect_description",
    "vehicle_info",
    "notes",
}


def normalize_extraction(
    extraction: ClaudeExtraction,
    *,
    source_text: str = "",
    operator_text: str = "",
    language: Optional[str] = None,
) -> ClaudeExtraction:
    """Normalize model or heuristic output before it can update dispatcher state.

    The application has several extractors with different quality profiles.
    This boundary keeps the UI contract stable: form fields are concise,
    schema-compatible, and dispatcher-facing.
    """
    raw_fields = extraction.form_fields.model_dump(exclude_unset=False)
    fields = normalize_form_dict(
        raw_fields,
        source_text=source_text,
        operator_text=operator_text,
        language=language or extraction.detected_language,
    )
    return ClaudeExtraction(
        form_fields=FormFields(**fields),
        suggestions=_normalize_suggestions(extraction.suggestions),
        highlight_keywords=[
            _clean_text(str(item))
            for item in extraction.highlight_keywords
            if _clean_text(str(item))
        ],
        priority_reasoning=_clean_text(extraction.priority_reasoning),
        detected_language=normalize_detected_language(extraction.detected_language),
    )


def normalize_form_dict(
    fields: dict[str, Any],
    *,
    source_text: str = "",
    operator_text: str = "",
    language: Optional[str] = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            out[key] = None
            continue
        if key in TEXT_FIELDS and isinstance(value, str):
            out[key] = _clean_text(value)
        else:
            out[key] = value

    out["incident_type"] = _normalize_incident_type(out.get("incident_type"))
    out["priority"] = _normalize_priority(out.get("priority"))
    out["injuries_reported"] = _normalize_yes_no_unknown(out.get("injuries_reported"))
    out["weapons_involved"] = _normalize_yes_no_unknown(out.get("weapons_involved"))
    out["num_victims"] = _normalize_int(out.get("num_victims"))
    out["callback_number"] = _normalize_phone(out.get("callback_number"))
    out["caller_name"] = _normalize_grounded_text(
        out.get("caller_name"),
        source_text=source_text,
        operator_text=operator_text,
    )

    out["location"] = normalize_location(
        out.get("location"),
        source_text=source_text,
        operator_text=operator_text,
        language=language,
    )
    out["cross_street"] = normalize_location(
        out.get("cross_street"),
        source_text=source_text,
        operator_text=operator_text,
        language=language,
        allow_plain=True,
        prefer_transcript_address=False,
    )

    for key in ("description", "victim_condition", "hazards", "suspect_description", "vehicle_info", "notes"):
        out[key] = _normalize_dispatcher_text(out.get(key), language=language)

    return out


def normalize_location(
    value: Any,
    *,
    source_text: str = "",
    operator_text: str = "",
    language: Optional[str] = None,
    allow_plain: bool = False,
    prefer_transcript_address: bool = True,
) -> Optional[str]:
    evidence_text = " ".join(part for part in (operator_text, source_text) if part)

    # The transcript is the source of truth. Prefer addresses extracted from
    # recognized speech/translation over any model-proposed value.
    if prefer_transcript_address:
        for candidate in (operator_text, source_text):
            extracted = extract_address(candidate)
            if extracted:
                return extracted

    cleaned = _clean_text(str(value or ""))
    if not cleaned:
        return None
    extracted_value = extract_address(cleaned)
    if extracted_value:
        return extracted_value if _is_grounded(extracted_value, evidence_text) else None
    if _looks_like_sentence(cleaned) or _contains_emergency_narrative(cleaned):
        return None
    if CYRILLIC_RE.search(cleaned) and not _is_english(language):
        cleaned = transliterate_ru(cleaned)
    if not allow_plain:
        return cleaned[:90] if _is_grounded(cleaned, evidence_text) else None
    return cleaned[:90] if _is_grounded(cleaned, evidence_text) else None


def extract_address(text: str) -> Optional[str]:
    """Extract only location evidence that appears in the transcript itself."""
    cleaned = _clean_text(text)
    if not cleaned:
        return None

    for pattern in EN_ADDRESS_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            if len(match.groups()) == 2:
                return _format_english_address(f"{match.group(1)} {match.group(2)}")
            return _format_english_address(match.group(1))

    for pattern in RU_ADDRESS_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        if len(match.groups()) == 3:
            marker, street_name, house = match.groups()
        else:
            marker, street_name, house = "улица", match.group(1), match.group(2)
        street_type = _street_type_from_ru(marker)
        street = transliterate_ru(street_name).strip(" .,-")
        return _format_english_address(f"{street} {street_type} {house}")

    return None


def normalize_detected_language(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("type", "code", "language", "value"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def transliterate_ru(text: str) -> str:
    table = {
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
        "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
        "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
        "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
        "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    }
    table.update({key.lower(): value.lower() for key, value in list(table.items())})
    transliterated = "".join(table.get(ch, ch) for ch in text)
    return _title_case_address(transliterated)


def _normalize_suggestions(suggestions: list[Suggestion]) -> list[Suggestion]:
    normalized: list[Suggestion] = []
    for item in suggestions:
        question = _normalize_dispatcher_text(item.question, language=None)
        trigger = _normalize_dispatcher_text(item.trigger, language=None) or ""
        rationale = _normalize_dispatcher_text(item.rationale, language=None) if item.rationale else None
        if not question:
            continue
        normalized.append(
            Suggestion(
                id=item.id,
                trigger=trigger,
                question=question,
                urgency=item.urgency,
                rationale=rationale,
                category=item.category,
                suggestion_type=item.suggestion_type,
            )
        )
    return normalized


def _normalize_incident_type(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    aliases = {
        "med": "medical",
        "ems": "medical",
        "medical emergency": "medical",
        "fire emergency": "fire",
        "law": "police",
        "law enforcement": "police",
        "vehicle": "traffic",
        "mva": "traffic",
        "accident": "traffic",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"medical", "fire", "police", "traffic", "other"} else None


def _normalize_priority(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized if normalized in {"P1", "P2", "P3", "P4"} else None


def _normalize_yes_no_unknown(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return value if isinstance(value, str) and value in {"yes", "no", "unknown"} else None
    aliases = {
        "yes": "yes", "y": "yes", "true": "yes",
        "no": "no", "n": "no", "false": "no",
        "unknown": "unknown", "unk": "unknown", "not sure": "unknown",
    }
    return aliases.get(value.strip().lower())


def _normalize_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else None
    return None


def _normalize_phone(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    digits = PHONE_DIGITS_RE.sub("", cleaned)
    return cleaned if len(digits) >= 7 else None


def _normalize_grounded_text(
    value: Any,
    *,
    source_text: str,
    operator_text: str,
) -> Optional[str]:
    cleaned = _clean_text(str(value or ""))
    if not cleaned:
        return None
    evidence_text = " ".join(part for part in (operator_text, source_text) if part)
    return cleaned if _is_grounded(cleaned, evidence_text) else None


def _normalize_dispatcher_text(value: Any, *, language: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = _clean_text(str(value))
    if not cleaned:
        return None
    if CYRILLIC_RE.search(cleaned) and not _is_english(language):
        return None
    return cleaned


def _street_type_from_ru(marker: str) -> str:
    lowered = marker.lower()
    if "просп" in lowered or "пр-т" in lowered:
        return "Avenue"
    if "переул" in lowered:
        return "Lane"
    if "проезд" in lowered:
        return "Drive"
    if "шоссе" in lowered:
        return "Road"
    if "площад" in lowered:
        return "Square"
    return "Street"


def _format_english_address(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    if re.fullmatch(r"\d{1,6}[A-Za-z0-9-]*", cleaned):
        return cleaned
    cleaned = re.sub(r"\b(street|avenue|road|boulevard|drive|lane|place|court)\b", lambda m: m.group(1).title(), cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(st|ave|rd|blvd|dr|ln|pl|ct)\.?\b", lambda m: _abbrev_to_street_type(m.group(1)), cleaned, flags=re.IGNORECASE)
    return _title_case_address(cleaned.strip(" ,.;:"))[:90]


def _is_grounded(value: str, evidence_text: str) -> bool:
    """Return True when important tokens in value are present in transcript text.

    This protects high-risk identity/location fields from LLM prompt leakage.
    The model may summarize descriptions, but addresses, cross streets, and
    names must have token evidence in recognized caller speech or translation.
    """
    if not value or not evidence_text:
        return False
    value_tokens = _evidence_tokens(value)
    evidence_tokens = set(_evidence_tokens(evidence_text))
    if not value_tokens:
        return False

    digits = [token for token in value_tokens if any(ch.isdigit() for ch in token)]
    if digits and not all(token in evidence_tokens for token in digits):
        return False

    significant = [
        token for token in value_tokens
        if token not in {
            "street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
            "drive", "dr", "lane", "ln", "way", "place", "pl", "court", "ct",
            "mr", "mrs", "ms", "miss",
        }
    ]
    if not significant:
        return bool(digits)
    return all(token in evidence_tokens for token in significant)


def _evidence_tokens(text: str) -> list[str]:
    expanded = text
    if CYRILLIC_RE.search(text):
        expanded = f"{text} {transliterate_ru(text)}"
    return [token.lower() for token in WORD_RE.findall(expanded)]


def _abbrev_to_street_type(value: str) -> str:
    return {
        "st": "Street",
        "ave": "Avenue",
        "rd": "Road",
        "blvd": "Boulevard",
        "dr": "Drive",
        "ln": "Lane",
        "pl": "Place",
        "ct": "Court",
    }.get(value.lower(), value.title())


def _title_case_address(value: str) -> str:
    keep_upper = {"NW", "NE", "SW", "SE"}
    words = []
    for word in value.split():
        stripped = word.strip()
        if stripped.upper() in keep_upper or any(ch.isdigit() for ch in stripped):
            words.append(stripped)
        else:
            words.append(stripped[:1].upper() + stripped[1:])
    return " ".join(words)


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" \t\r\n\"'")
    cleaned = cleaned.replace(" ,", ",").replace(" .", ".")
    return cleaned or None


def _looks_like_sentence(value: str) -> bool:
    return len(value.split()) > 8 or any(mark in value for mark in ".!?")


def _contains_emergency_narrative(value: str) -> bool:
    lowered = value.lower()
    narrative_terms = {
        "fire", "smoke", "flame", "help", "children", "cry", "пожар", "дым",
        "огонь", "помог", "дет", "крик",
    }
    return any(term in lowered for term in narrative_terms)


def _is_english(language: Optional[str]) -> bool:
    return bool(language and language.lower().startswith("en"))
