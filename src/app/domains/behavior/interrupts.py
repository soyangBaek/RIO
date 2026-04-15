from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ActivityState, RuntimeState


class InterruptAction(str, Enum):
    ALLOW = "allow"
    DROP = "drop"
    DEFER_INTENT = "defer_intent"
    HOLD_ALERT = "hold_alert"


@dataclass(slots=True)
class InterruptDecision:
    action: InterruptAction
    reason: str
    deferred_payload: dict[str, object] | None = None
    held_events: list[Event] = field(default_factory=list)


def _intent_name(event: Event) -> str | None:
    return event.payload.get("intent") if event.topic == topics.VOICE_INTENT_DETECTED else None


def evaluate_interrupt(state: RuntimeState, event: Event) -> InterruptDecision:
    """Apply activity-level interrupt rules before the reducers run."""

    current = state.activity_state
    kind = state.extended.active_executing_kind
    intent_name = _intent_name(event)

    if current == ActivityState.ALERTING:
        if event.topic in {topics.SYSTEM_ALERT_TIMEOUT, topics.TIMER_EXPIRED}:
            return InterruptDecision(InterruptAction.ALLOW, "alert_event")
        if intent_name in {"system.ack", "system.cancel"}:
            return InterruptDecision(InterruptAction.ALLOW, "alert_ack")
        return InterruptDecision(InterruptAction.DROP, "alerting_lock")

    if current != ActivityState.EXECUTING:
        return InterruptDecision(InterruptAction.ALLOW, "not_executing")

    if kind == ActionKind.PHOTO:
        if event.topic == topics.TIMER_EXPIRED:
            return InterruptDecision(InterruptAction.HOLD_ALERT, "photo_holds_timer", held_events=[event])
        if intent_name in {"system.ack", "system.cancel"}:
            return InterruptDecision(InterruptAction.ALLOW, "photo_control")
        if event.topic == topics.VOICE_INTENT_DETECTED:
            return InterruptDecision(InterruptAction.DROP, "photo_lock")
        return InterruptDecision(InterruptAction.ALLOW, "photo_non_intent")

    if kind in {ActionKind.GAME, ActionKind.DANCE}:
        if event.topic == topics.TIMER_EXPIRED:
            return InterruptDecision(InterruptAction.ALLOW, "high_priority_alert")
        if intent_name in {"system.ack", "system.cancel"}:
            return InterruptDecision(InterruptAction.ALLOW, "long_action_control")
        if event.topic == topics.VOICE_INTENT_DETECTED:
            return InterruptDecision(InterruptAction.DROP, "long_action_lock")
        return InterruptDecision(InterruptAction.ALLOW, "long_action_non_intent")

    if kind in {ActionKind.SMARTHOME, ActionKind.WEATHER, ActionKind.TIMER_SETUP}:
        if event.topic == topics.TIMER_EXPIRED:
            return InterruptDecision(InterruptAction.ALLOW, "high_priority_alert")
        if event.topic == topics.VOICE_INTENT_DETECTED:
            return InterruptDecision(
                InterruptAction.DEFER_INTENT,
                "store_latest_intent",
                deferred_payload=dict(event.payload),
            )
        return InterruptDecision(InterruptAction.ALLOW, "short_action_non_intent")

    return InterruptDecision(InterruptAction.ALLOW, "fallback_allow")
