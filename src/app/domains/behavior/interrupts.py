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

    if current == ActivityState.LISTENING:
        # 음성 인식 도중에는 시각 이벤트(face/gesture)가 oneshot 이나 context
        # 전이를 만들지 않도록 전부 DROP. 사용자가 말하는 동안 손·표정 움직임이
        # 반응을 유발해 ASR 결과와 충돌하는 것을 방지한다. 음성(VOICE_*) 과
        # 터치·타이머 이벤트는 그대로 통과.
        if event.topic in {
            topics.VISION_FACE_DETECTED,
            topics.VISION_FACE_LOST,
            topics.VISION_FACE_MOVED,
            topics.VISION_GESTURE_DETECTED,
        }:
            return InterruptDecision(InterruptAction.DROP, "listening_vision_lock")
        return InterruptDecision(InterruptAction.ALLOW, "listening_non_vision")

    if current != ActivityState.EXECUTING:
        return InterruptDecision(InterruptAction.ALLOW, "not_executing")

    if kind == ActionKind.PHOTO:
        if event.topic == topics.TIMER_EXPIRED:
            return InterruptDecision(InterruptAction.HOLD_ALERT, "photo_holds_timer", held_events=[event])
        # 카운트다운 + 촬영 동안에는 사용자에게서 오는 모든 이벤트를 막는다.
        # 예외는 "멈춰줘"(system.cancel) 하나. 촬영 도중 제스처·터치·다른 음성
        # 명령이 oneshot / intent 로 새 나가지 않도록 명시적으로 DROP.
        if intent_name == "system.cancel":
            return InterruptDecision(InterruptAction.ALLOW, "photo_cancel")
        if event.topic in {
            topics.VOICE_INTENT_DETECTED,
            topics.VOICE_INTENT_UNKNOWN,
            topics.VISION_GESTURE_DETECTED,
            topics.TOUCH_TAP_DETECTED,
            topics.TOUCH_STROKE_DETECTED,
        }:
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

    if kind == ActionKind.SING:
        if event.topic == topics.TIMER_EXPIRED:
            return InterruptDecision(InterruptAction.ALLOW, "high_priority_alert")
        if intent_name in {"system.ack", "system.cancel"}:
            return InterruptDecision(InterruptAction.ALLOW, "long_action_control")
        if event.topic == topics.VOICE_INTENT_DETECTED:
            return InterruptDecision(InterruptAction.DROP, "sing_lock")
        if event.topic == topics.VISION_GESTURE_DETECTED:
            return InterruptDecision(InterruptAction.DROP, "sing_gesture_block")
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
