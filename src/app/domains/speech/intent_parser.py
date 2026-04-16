from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from src.app.core.config import resolve_repo_path


DEFAULT_INTENT_MATCH_CONFIDENCE_MIN = 0.6


@dataclass(slots=True)
class IntentParseResult:
    intent: str | None
    confidence: float
    text: str
    normalized_text: str
    matched_alias: str | None = None
    reason: str | None = None
    payload: dict[str, object] = field(default_factory=dict)

    @property
    def is_known(self) -> bool:
        return self.intent is not None


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"[!?.,]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


@lru_cache(maxsize=4)
def load_triggers(path: str = "configs/triggers.yaml") -> dict[str, list[str]]:
    try:
        with resolve_repo_path(path).open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        data = {}
    intents = data.get("intents", {})
    normalized: dict[str, list[str]] = {}
    for intent, aliases in intents.items():
        normalized[intent] = [normalize_text(alias) for alias in aliases or []]
    return normalized


def _token_overlap_score(normalized_text: str, alias: str) -> float:
    if not normalized_text or not alias:
        return 0.0
    if normalized_text == alias:
        return 1.0
    if alias in normalized_text:
        return 0.94
    if normalized_text in alias:
        return 0.88
    text_tokens = set(normalized_text.split())
    alias_tokens = set(alias.split())
    if not text_tokens or not alias_tokens:
        return 0.0
    overlap = len(text_tokens & alias_tokens)
    if not overlap:
        return 0.0
    return overlap / max(len(alias_tokens), len(text_tokens))


def _parse_dynamic_smarthome(
    text: str,
    normalized_text: str,
    *,
    stt_confidence: float,
) -> IntentParseResult | None:
    temp_match = re.search(r"(-?\d{1,2})\s*도(?:로)?", text)
    if temp_match is None:
        temp_match = re.search(r"(-?\d{1,2})\s*(?:degrees?|c)\b", normalized_text)
    if temp_match is None:
        return None

    intent_keywords = (
        "온도",
        "temperature",
        "맞춰",
        "설정",
        "set",
        "에어컨",
        "aircon",
        "air conditioner",
    )
    if not any(keyword in normalized_text for keyword in intent_keywords):
        return None

    temperature_c = int(temp_match.group(1))
    if temperature_c < 16 or temperature_c > 30:
        return IntentParseResult(
            intent=None,
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            reason="temperature_out_of_range",
        )

    return IntentParseResult(
        intent="smarthome.aircon.set_temperature",
        confidence=stt_confidence,
        text=text,
        normalized_text=normalized_text,
        matched_alias="__dynamic_aircon_temperature__",
        payload={
            "device_key": "aircon",
            "action": "set_temperature",
            "temperature_c": temperature_c,
        },
    )


def parse_intent(
    text: str,
    *,
    stt_confidence: float = 1.0,
    intent_match_confidence_min: float = DEFAULT_INTENT_MATCH_CONFIDENCE_MIN,
    triggers: dict[str, list[str]] | None = None,
    triggers_path: str = "configs/triggers.yaml",
) -> IntentParseResult:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return IntentParseResult(
            intent=None,
            confidence=0.0,
            text=text,
            normalized_text=normalized_text,
            reason="empty_text",
        )
    if stt_confidence < intent_match_confidence_min:
        return IntentParseResult(
            intent=None,
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            reason="low_stt_confidence",
        )

    dynamic_smarthome = _parse_dynamic_smarthome(
        text,
        normalized_text,
        stt_confidence=stt_confidence,
    )
    if dynamic_smarthome is not None:
        return dynamic_smarthome

    trigger_map = triggers or load_triggers(triggers_path)
    best_intent: str | None = None
    best_alias: str | None = None
    best_score = 0.0

    for intent, aliases in trigger_map.items():
        for alias in aliases:
            score = _token_overlap_score(normalized_text, alias)
            if score > best_score:
                best_intent = intent
                best_alias = alias
                best_score = score

    final_confidence = min(stt_confidence, best_score)
    if best_intent is None or final_confidence < intent_match_confidence_min:
        return IntentParseResult(
            intent=None,
            confidence=final_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias=best_alias,
            reason="unknown_intent",
        )

    return IntentParseResult(
        intent=best_intent,
        confidence=final_confidence,
        text=text,
        normalized_text=normalized_text,
        matched_alias=best_alias,
    )
