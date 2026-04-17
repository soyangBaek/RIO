from __future__ import annotations

from datetime import datetime

from src.app.core.events.models import Event
from src.app.core.events import topics
from src.app.core.state.models import ActivityState, ActionKind, intent_to_action_kind


def transition_activity(
    current: ActivityState,
    event: Event,
    active_kind: ActionKind | None = None,
    *,
    now: datetime | None = None,
) -> tuple[ActivityState, ActionKind | None]:
    del now

    if current == ActivityState.ALERTING:
        intent = event.payload.get("intent")
        if event.topic == topics.SYSTEM_ALERT_TIMEOUT or intent == "system.ack":
            return ActivityState.IDLE, None
        return current, active_kind

    if event.topic == topics.TIMER_EXPIRED:
        return ActivityState.ALERTING, None

    if current == ActivityState.IDLE:
        if event.topic == topics.VOICE_ACTIVITY_STARTED:
            return ActivityState.LISTENING, None
        return current, active_kind

    if current == ActivityState.LISTENING:
        if event.topic == topics.VOICE_ACTIVITY_ENDED:
            return ActivityState.IDLE, None
        if event.topic == topics.VOICE_INTENT_UNKNOWN:
            return ActivityState.IDLE, None
        if event.topic == topics.VOICE_INTENT_DETECTED:
            intent = event.payload.get("intent")
            if intent in {"system.cancel", "system.ack"}:
                return ActivityState.IDLE, None
            kind = intent_to_action_kind(intent)
            if kind is None:
                return ActivityState.IDLE, None
            return ActivityState.EXECUTING, kind
        return current, active_kind

    if current == ActivityState.EXECUTING:
        if event.topic in {topics.TASK_SUCCEEDED, topics.TASK_FAILED}:
            return ActivityState.IDLE, None
        if event.topic == topics.VOICE_INTENT_DETECTED:
            intent = event.payload.get("intent")
            if intent in {"system.cancel", "system.ack"} and active_kind in {
                ActionKind.DANCE,
                ActionKind.GAME,
            }:
                return ActivityState.IDLE, None
        return current, active_kind

    return current, active_kind

