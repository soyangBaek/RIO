from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from src.app.core.config import resolve_repo_path
from src.app.domains.speech.text_normalizer import KoreanCommandNormalizer


DEFAULT_INTENT_MATCH_CONFIDENCE_MIN = 0.6
_TEXT_NORMALIZER = KoreanCommandNormalizer()


@dataclass(slots=True)
class IntentParseResult:
    intent: str | None
    confidence: float
    text: str
    normalized_text: str
    matched_alias: str | None = None
    reason: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    normalization_replacements: list[dict[str, object]] = field(default_factory=list)

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
    compact_text = normalized_text.replace(" ", "")
    compact_alias = alias.replace(" ", "")
    if compact_text == compact_alias:
        return 0.98
    if alias in normalized_text:
        return 0.94
    if compact_alias and compact_alias in compact_text:
        return 0.92
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
    compact = normalized_text.replace(" ", "")

    def has_any(*words: str) -> bool:
        return any(word in normalized_text or word in compact for word in words)

    def result(intent: str, *, matched_alias: str, payload: dict[str, object] | None = None) -> IntentParseResult:
        return IntentParseResult(
            intent=intent,
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias=matched_alias,
            payload=dict(payload or {}),
        )

    temp_match = re.search(r"(-?\d{1,2})\s*도(?:로)?", text)
    if temp_match is None:
        temp_match = re.search(r"(-?\d{1,2})\s*(?:degrees?|c)\b", normalized_text)
    if temp_match is not None:
        heater_keywords = ("난방", "히터", "heater", "heating", "보일러")
        aircon_keywords = (
            "온도",
            "temperature",
            "맞춰",
            "설정",
            "set",
            "에어컨",
            "aircon",
            "air conditioner",
        )
        temperature_c = int(temp_match.group(1))

        if any(keyword in normalized_text for keyword in heater_keywords):
            if temperature_c < 16 or temperature_c > 30:
                return IntentParseResult(
                    intent=None,
                    confidence=stt_confidence,
                    text=text,
                    normalized_text=normalized_text,
                    reason="temperature_out_of_range",
                )
            return result(
                "smarthome.heater.set_temperature",
                matched_alias="__dynamic_heater_temperature__",
                payload={
                    "device_key": "heater",
                    "action": "set_temperature",
                    "temperature_c": temperature_c,
                },
            )

        if any(keyword in normalized_text for keyword in aircon_keywords):
            if temperature_c < 16 or temperature_c > 30:
                return IntentParseResult(
                    intent=None,
                    confidence=stt_confidence,
                    text=text,
                    normalized_text=normalized_text,
                    reason="temperature_out_of_range",
                )

            return result(
                "smarthome.aircon.set_temperature",
                matched_alias="__dynamic_aircon_temperature__",
                payload={
                    "device_key": "aircon",
                    "action": "set_temperature",
                    "temperature_c": temperature_c,
                },
            )

    if has_any("에어컨", "aircon", "air conditioner", "ac", "냉방"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지", "멈춰"):
            return result("smarthome.aircon.off", matched_alias="__dynamic_aircon_off__")
        if has_any("켜줘", "켜", "켜기", "on", "틀어줘"):
            return result("smarthome.aircon.on", matched_alias="__dynamic_aircon_on__")

    if has_any("난방", "히터", "heater", "heating", "보일러"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지", "멈춰"):
            return result("smarthome.heater.off", matched_alias="__dynamic_heater_off__")
        if has_any("켜줘", "켜", "켜기", "on", "틀어줘"):
            return result("smarthome.heater.on", matched_alias="__dynamic_heater_on__")

    if has_any("간접등", "간접 조명", "무드등", "indirect light", "mood light"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지"):
            return result("smarthome.indirect_light.off", matched_alias="__dynamic_indirect_light_off__")
        if has_any("켜줘", "켜", "켜기", "on"):
            return result("smarthome.indirect_light.on", matched_alias="__dynamic_indirect_light_on__")

    if has_any("조명", "전등", "불", "light", "lamp"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지"):
            return result("smarthome.light.off", matched_alias="__dynamic_light_off__")
        if has_any("켜줘", "켜", "켜기", "on"):
            return result("smarthome.light.on", matched_alias="__dynamic_light_on__")

    if has_any("로봇청소기", "로봇 청소기", "청소기", "robot cleaner", "vacuum", "cleaner"):
        if has_any("멈춰줘", "멈춰", "정지", "stop", "꺼줘", "꺼", "끄기", "off"):
            return result("smarthome.robot_cleaner.stop", matched_alias="__dynamic_robot_cleaner_stop__")
        if has_any("실행", "시작", "돌려", "켜줘", "켜", "켜기", "on", "틀어줘", "start"):
            return result("smarthome.robot_cleaner.start", matched_alias="__dynamic_robot_cleaner_start__")

    if has_any("공기청정기", "공기 청정기", "air purifier", "purifier"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지", "멈춰"):
            return result("smarthome.air_purifier.off", matched_alias="__dynamic_air_purifier_off__")
        if has_any("켜줘", "켜", "켜기", "on", "틀어줘"):
            return result("smarthome.air_purifier.on", matched_alias="__dynamic_air_purifier_on__")

    if has_any("컴퓨터", "computer", "pc", "피씨"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지"):
            return result("smarthome.computer.off", matched_alias="__dynamic_computer_off__")
        if has_any("켜줘", "켜", "켜기", "on"):
            return result("smarthome.computer.on", matched_alias="__dynamic_computer_on__")

    if has_any("티비", "tv", "텔레비전", "teevee"):
        if has_any("꺼줘", "꺼", "끄기", "off", "정지"):
            return result("smarthome.tv.off", matched_alias="__dynamic_tv_off__")
        if has_any("켜줘", "켜", "켜기", "on"):
            return result("smarthome.tv.on", matched_alias="__dynamic_tv_on__")

    if has_any("음악", "노래", "music", "speaker"):
        if has_any("꺼줘", "꺼", "끄기", "off", "멈춰줘", "멈춰", "정지", "stop"):
            return result("smarthome.music.stop", matched_alias="__dynamic_music_stop__")
        if has_any("틀어줘", "틀어", "재생", "play", "켜줘", "켜", "켜기", "on"):
            return result("smarthome.music.play", matched_alias="__dynamic_music_play__")

    if has_any("다 꺼", "다꺼", "전부 꺼", "전부꺼", "모두 꺼", "모두꺼", "외출 모드", "외출모드", "turn everything off", "all off"):
        return result("smarthome.all.off", matched_alias="__dynamic_all_off__")

    return None


def _parse_dynamic_generic(
    text: str,
    normalized_text: str,
    *,
    stt_confidence: float,
) -> IntentParseResult | None:
    compact = normalized_text.replace(" ", "")

    def has_any(*words: str) -> bool:
        return any(word in normalized_text or word in compact for word in words)

    if has_any("댄스모드", "댄스", "춤춰", "dance mode", "dance"):
        return IntentParseResult(
            intent="dance.start",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_dance__",
        )

    if has_any("사진", "photo", "picture") and has_any("찍어", "찍자", "take", "capture", "please", "사진"):
        return IntentParseResult(
            intent="camera.capture",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_camera__",
        )

    if has_any("게임모드", "게임 모드", "game mode", "게임"):
        return IntentParseResult(
            intent="ui.game_mode.enter",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_game_mode__",
        )

    if has_any("날씨", "weather"):
        return IntentParseResult(
            intent="weather.current",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_weather__",
        )

    timer_hint = re.search(r"(\d+\s*(시간|분|초)|오전|오후|am|pm|\d+\s*시)", normalized_text)
    if timer_hint and has_any("알려줘", "타이머", "알람", "timer", "later", "뒤", "후", "맞춰줘"):
        return IntentParseResult(
            intent="timer.create",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_timer__",
        )

    if has_any("취소", "cancel", "그만"):
        return IntentParseResult(
            intent="system.cancel",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_cancel__",
        )

    if has_any("알겠어", "확인", "오케이", "okay", "ok"):
        return IntentParseResult(
            intent="system.ack",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_ack__",
        )

    return None


def parse_intent(
    text: str,
    *,
    stt_confidence: float = 1.0,
    intent_match_confidence_min: float = DEFAULT_INTENT_MATCH_CONFIDENCE_MIN,
    triggers: dict[str, list[str]] | None = None,
    triggers_path: str = "configs/triggers.yaml",
) -> IntentParseResult:
    normalization = _TEXT_NORMALIZER.normalize(text)
    normalized_text = normalize_text(normalization.normalized_text)
    if not normalized_text:
        return IntentParseResult(
            intent=None,
            confidence=0.0,
            text=text,
            normalized_text=normalized_text,
            reason="empty_text",
            normalization_replacements=normalization.replacements,
        )
    if stt_confidence < intent_match_confidence_min:
        return IntentParseResult(
            intent=None,
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            reason="low_stt_confidence",
            normalization_replacements=normalization.replacements,
        )

    dynamic_smarthome = _parse_dynamic_smarthome(
        text,
        normalized_text,
        stt_confidence=stt_confidence,
    )
    if dynamic_smarthome is not None:
        dynamic_smarthome.normalization_replacements = normalization.replacements
        return dynamic_smarthome

    dynamic_generic = _parse_dynamic_generic(
        text,
        normalized_text,
        stt_confidence=stt_confidence,
    )
    if dynamic_generic is not None:
        dynamic_generic.normalization_replacements = normalization.replacements
        return dynamic_generic

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
            normalization_replacements=normalization.replacements,
        )

    return IntentParseResult(
        intent=best_intent,
        confidence=final_confidence,
        text=text,
        normalized_text=normalized_text,
        matched_alias=best_alias,
        normalization_replacements=normalization.replacements,
    )
