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

    # 공식 발화만 허용. alias/영어/유사 표현은 의도적으로 제거 — 단일 발화
    # 원칙 (docs/user-utterance-scenarios.md) 에 맞춘다. STT 오인식 보정은
    # 개별 intent 블록 안 keyword 리스트에 점진 추가.

    if has_any("에어컨"):
        if has_any("꺼줘"):
            return result("smarthome.aircon.off", matched_alias="__dynamic_aircon_off__")
        if has_any("켜줘"):
            return result("smarthome.aircon.on", matched_alias="__dynamic_aircon_on__")

    if has_any("난방"):
        if has_any("꺼줘"):
            return result("smarthome.heater.off", matched_alias="__dynamic_heater_off__")
        if has_any("켜줘"):
            return result("smarthome.heater.on", matched_alias="__dynamic_heater_on__")

    # 간접등은 whisper 가 "간접든/간접 등/간접 던" 등으로 자주 쪼개/바꿔 낸다.
    # compact 매칭이 "간접등" 을 잡도록 유지하되, 관찰된 오인식은 여기 추가.
    if has_any("간접등", "간접든"):
        if has_any("꺼줘"):
            return result("smarthome.indirect_light.off", matched_alias="__dynamic_indirect_light_off__")
        if has_any("켜줘"):
            return result("smarthome.indirect_light.on", matched_alias="__dynamic_indirect_light_on__")

    # "거실 등" 은 whisper 가 "거실등/거실 등/거실 덩" 등으로 다양하게 낸다.
    # compact 매칭으로 공백 유무 모두 흡수.
    if has_any("거실 등", "거실등"):
        if has_any("꺼줘"):
            return result("smarthome.light.off", matched_alias="__dynamic_light_off__")
        if has_any("켜줘"):
            return result("smarthome.light.on", matched_alias="__dynamic_light_on__")

    if has_any("청소기"):
        if has_any("정지"):
            return result("smarthome.robot_cleaner.stop", matched_alias="__dynamic_robot_cleaner_stop__")
        if has_any("돌려줘"):
            return result("smarthome.robot_cleaner.start", matched_alias="__dynamic_robot_cleaner_start__")

    if has_any("공기청정기"):
        if has_any("꺼줘"):
            return result("smarthome.air_purifier.off", matched_alias="__dynamic_air_purifier_off__")
        if has_any("켜줘"):
            return result("smarthome.air_purifier.on", matched_alias="__dynamic_air_purifier_on__")

    if has_any("컴퓨터"):
        if has_any("꺼줘"):
            return result("smarthome.computer.off", matched_alias="__dynamic_computer_off__")
        if has_any("켜줘"):
            return result("smarthome.computer.on", matched_alias="__dynamic_computer_on__")

    if has_any("티비"):
        if has_any("꺼줘"):
            return result("smarthome.tv.off", matched_alias="__dynamic_tv_off__")
        if has_any("켜줘"):
            return result("smarthome.tv.on", matched_alias="__dynamic_tv_on__")

    if has_any("음악"):
        if has_any("꺼줘"):
            return result("smarthome.music.stop", matched_alias="__dynamic_music_stop__")
        if has_any("틀어줘"):
            return result("smarthome.music.play", matched_alias="__dynamic_music_play__")

    if has_any("다 꺼줘", "다꺼줘"):
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

    # 공식 발화만. 영어/유사 표현 제거.

    if has_any("노래 해줘", "노래해줘"):
        return IntentParseResult(
            intent="sing.start",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_sing__",
        )

    if has_any("춤춰줘"):
        return IntentParseResult(
            intent="dance.start",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_dance__",
        )

    if has_any("사진") and has_any("찍어줘"):
        return IntentParseResult(
            intent="camera.capture",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_camera__",
        )

    if has_any("게임 모드", "게임모드"):
        return IntentParseResult(
            intent="ui.game_mode.enter",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_game_mode__",
        )

    if has_any("날씨") and has_any("알려줘"):
        return IntentParseResult(
            intent="weather.current",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_weather__",
        )

    # 타이머는 숫자+단위 필수 유지 ("N분 뒤에 알려줘").
    timer_hint = re.search(r"\d+\s*(분|초)", normalized_text)
    if timer_hint and has_any("뒤에 알려줘", "뒤에알려줘"):
        return IntentParseResult(
            intent="timer.create",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_timer__",
        )

    # "멈춰줘" 는 단독 발화만 cancel 로 처리한다. "음악 멈춰줘" 같이 다른
    # 키워드와 결합된 발화는 substring 매칭으로 잡히면 smarthome 등
    # 다른 의도를 가로채기 때문에, compact 형태의 exact match 로 한정.
    if compact == "멈춰줘":
        return IntentParseResult(
            intent="system.cancel",
            confidence=stt_confidence,
            text=text,
            normalized_text=normalized_text,
            matched_alias="__dynamic_cancel__",
        )

    if has_any("확인"):
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
