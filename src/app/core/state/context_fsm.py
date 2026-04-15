from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.app.core.events.models import Event
from src.app.core.events import topics
from src.app.core.state.models import ContextState, ExtendedState


DEFAULT_THRESHOLDS = {
    "presence": {
        "face_lost_timeout_ms": 800,
        "away_timeout_ms": 60_000,
        "welcome_min_away_ms": 3_000,
        "face_moved_sample_hz": 10,
    },
    "behavior": {
        "idle_to_sleepy_timeout_ms": 120_000,
        "engaged_to_idle_timeout_ms": 5_000,
        "intent_cooldown_ms": 1_500,
        "startled_oneshot_min_ms": 600,
    },
}


@dataclass(frozen=True, slots=True)
class ContextThresholds:
    away_timeout_ms: int = 60_000
    idle_to_sleepy_timeout_ms: int = 120_000
    engaged_to_idle_timeout_ms: int = 5_000
    welcome_min_away_ms: int = 3_000
    face_lost_timeout_ms: int = 800


def load_thresholds(path: str | Path = "configs/thresholds.yaml") -> ContextThresholds:
    data = DEFAULT_THRESHOLDS
    cfg_path = Path(path)
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        data = {
            "presence": {**DEFAULT_THRESHOLDS["presence"], **loaded.get("presence", {})},
            "behavior": {**DEFAULT_THRESHOLDS["behavior"], **loaded.get("behavior", {})},
        }
    return ContextThresholds(
        away_timeout_ms=int(data["presence"]["away_timeout_ms"]),
        idle_to_sleepy_timeout_ms=int(data["behavior"]["idle_to_sleepy_timeout_ms"]),
        engaged_to_idle_timeout_ms=int(data["behavior"]["engaged_to_idle_timeout_ms"]),
        welcome_min_away_ms=int(data["presence"]["welcome_min_away_ms"]),
        face_lost_timeout_ms=int(data["presence"]["face_lost_timeout_ms"]),
    )


def _age_ms(reference: datetime | None, now: datetime) -> float:
    if reference is None:
        return 0.0
    return max((now - reference).total_seconds() * 1000.0, 0.0)


def _is_user_evidence(event: Event) -> bool:
    return event.topic in {
        topics.VISION_FACE_DETECTED,
        topics.VOICE_ACTIVITY_STARTED,
        topics.TOUCH_TAP_DETECTED,
        topics.TOUCH_STROKE_DETECTED,
    }


def _is_interaction(event: Event) -> bool:
    return event.topic in {
        topics.VOICE_ACTIVITY_STARTED,
        topics.VOICE_INTENT_DETECTED,
        topics.TOUCH_TAP_DETECTED,
        topics.TOUCH_STROKE_DETECTED,
        topics.VISION_GESTURE_DETECTED,
    }


def _long_idle(extended: ExtendedState, thresholds: ContextThresholds, now: datetime) -> bool:
    reference = extended.last_interaction_at or extended.last_user_evidence_at
    return reference is not None and _age_ms(reference, now) >= thresholds.idle_to_sleepy_timeout_ms


def _no_face_long_timeout(extended: ExtendedState, thresholds: ContextThresholds, now: datetime) -> bool:
    if extended.face_present:
        return False
    reference = extended.last_face_seen_at or extended.last_user_evidence_at
    return reference is not None and _age_ms(reference, now) >= thresholds.away_timeout_ms


def _no_interaction_for_a_while(
    extended: ExtendedState,
    thresholds: ContextThresholds,
    now: datetime,
) -> bool:
    return (
        extended.last_interaction_at is not None
        and _age_ms(extended.last_interaction_at, now) >= thresholds.engaged_to_idle_timeout_ms
    )


def transition_context(
    current: ContextState,
    event: Event,
    extended: ExtendedState,
    thresholds: ContextThresholds | None = None,
    *,
    now: datetime | None = None,
) -> ContextState:
    limits = thresholds or load_thresholds()
    when = now or event.timestamp

    if current == ContextState.AWAY:
        if _is_user_evidence(event):
            return ContextState.IDLE
        return current

    if current == ContextState.SLEEPY:
        if event.topic == topics.VISION_FACE_DETECTED:
            return ContextState.IDLE
        if _no_face_long_timeout(extended, limits, when):
            return ContextState.AWAY
        return current

    if current == ContextState.IDLE:
        if _long_idle(extended, limits, when):
            return ContextState.SLEEPY
        if _no_face_long_timeout(extended, limits, when):
            return ContextState.AWAY
        if extended.face_present and _is_interaction(event):
            return ContextState.ENGAGED
        return current

    if current == ContextState.ENGAGED:
        if _long_idle(extended, limits, when):
            return ContextState.SLEEPY
        if _no_face_long_timeout(extended, limits, when):
            return ContextState.AWAY
        if _no_interaction_for_a_while(extended, limits, when):
            return ContextState.IDLE
        return current

    return current

