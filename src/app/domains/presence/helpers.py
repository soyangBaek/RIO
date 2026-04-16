from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import yaml

from src.app.core.config import resolve_repo_path
from src.app.core.state.models import ActivityState, ContextState, ExtendedState


DEFAULT_PRESENCE_THRESHOLDS = {
    "face_lost_timeout_ms": 800,
    "welcome_min_away_ms": 3000,
}


@dataclass(slots=True)
class PresenceThresholds:
    face_lost_timeout_ms: int = DEFAULT_PRESENCE_THRESHOLDS["face_lost_timeout_ms"]
    welcome_min_away_ms: int = DEFAULT_PRESENCE_THRESHOLDS["welcome_min_away_ms"]


@dataclass(slots=True)
class PresenceFacts:
    is_searching_for_user: bool
    recent_face_loss: bool
    just_reappeared: bool
    confirmed_user_and_interacting: bool


def load_presence_thresholds(path: str = "configs/thresholds.yaml") -> PresenceThresholds:
    try:
        with resolve_repo_path(path).open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        data = {}
    presence = data.get("presence", {})
    return PresenceThresholds(
        face_lost_timeout_ms=int(
            presence.get("face_lost_timeout_ms", DEFAULT_PRESENCE_THRESHOLDS["face_lost_timeout_ms"])
        ),
        welcome_min_away_ms=int(
            presence.get("welcome_min_away_ms", DEFAULT_PRESENCE_THRESHOLDS["welcome_min_away_ms"])
        ),
    )


def is_searching_for_user(activity_state: ActivityState, extended: ExtendedState) -> bool:
    return activity_state == ActivityState.LISTENING and not extended.face_present


def recent_face_loss(
    extended: ExtendedState,
    thresholds: PresenceThresholds | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    thresholds = thresholds or PresenceThresholds()
    now = now or datetime.now(timezone.utc)
    if extended.face_present or extended.last_face_seen_at is None:
        return False
    delta_ms = (now - extended.last_face_seen_at).total_seconds() * 1000.0
    return delta_ms < thresholds.face_lost_timeout_ms


def just_reappeared(
    previous_context: ContextState | None,
    current_context: ContextState,
    extended: ExtendedState,
    thresholds: PresenceThresholds | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    thresholds = thresholds or PresenceThresholds()
    now = now or datetime.now(timezone.utc)
    if previous_context not in {ContextState.AWAY, ContextState.SLEEPY}:
        return False
    if current_context != ContextState.IDLE:
        return False
    if extended.away_started_at is None:
        return False
    delta_ms = (now - extended.away_started_at).total_seconds() * 1000.0
    return delta_ms >= thresholds.welcome_min_away_ms


def confirmed_user_and_interacting(
    extended: ExtendedState,
    *,
    interaction_event_seen: bool,
) -> bool:
    return bool(extended.face_present and interaction_event_seen)


def derive_presence_facts(
    context_state: ContextState,
    activity_state: ActivityState,
    extended: ExtendedState,
    *,
    interaction_event_seen: bool = False,
    thresholds: PresenceThresholds | None = None,
    now: datetime | None = None,
) -> PresenceFacts:
    thresholds = thresholds or PresenceThresholds()
    previous_context = extended.previous_context_state
    return PresenceFacts(
        is_searching_for_user=is_searching_for_user(activity_state, extended),
        recent_face_loss=recent_face_loss(extended, thresholds, now=now),
        just_reappeared=just_reappeared(previous_context, context_state, extended, thresholds, now=now),
        confirmed_user_and_interacting=confirmed_user_and_interacting(
            extended,
            interaction_event_seen=interaction_event_seen,
        ),
    )
