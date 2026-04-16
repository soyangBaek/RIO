"""T-009: Activity FSM – 전이 규칙.

state-machine.md §4 기준.
Idle/Listening/Executing/Alerting 전이만 담당.
인터럽트 정책은 domains/behavior/interrupts.py 에서 처리.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.models import ActivityState, ExecutingKind
from src.app.core.state.store import Store

# intent → ExecutingKind 매핑
INTENT_TO_KIND = {
    "camera.capture": ExecutingKind.PHOTO,
    "weather.current": ExecutingKind.WEATHER,
    "smarthome.aircon.on": ExecutingKind.SMARTHOME,
    "smarthome.light.on": ExecutingKind.SMARTHOME,
    "smarthome.robot_cleaner.start": ExecutingKind.SMARTHOME,
    "smarthome.tv.on": ExecutingKind.SMARTHOME,
    "smarthome.music.play": ExecutingKind.SMARTHOME,
    "timer.create": ExecutingKind.TIMER_SETUP,
    "dance.start": ExecutingKind.DANCE,
    "ui.game_mode.enter": ExecutingKind.GAME,
}


def resolve_executing_kind(intent: str) -> Optional[ExecutingKind]:
    """intent 문자열에서 ExecutingKind 를 결정."""
    if intent in INTENT_TO_KIND:
        return INTENT_TO_KIND[intent]
    # smarthome.* 패턴
    if intent.startswith("smarthome."):
        return ExecutingKind.SMARTHOME
    return None


def activity_transition(
    store: Store,
    event: Event,
    config: Dict[str, Any],
) -> Optional[Tuple[ActivityState, ActivityState, Optional[ExecutingKind]]]:
    """Activity FSM 전이 반환.

    (from_state, to_state, executing_kind_or_None).
    전이 없으면 None.
    """
    current = store.activity_state
    topic = event.topic

    # ── Idle ─────────────────────────────────────────────────
    if current == ActivityState.IDLE:
        # → Listening on voice_started
        if topic == Topics.VOICE_ACTIVITY_STARTED:
            return (ActivityState.IDLE, ActivityState.LISTENING, None)

        # → Alerting on timer_expired or system_event
        if topic == Topics.TIMER_EXPIRED:
            return (ActivityState.IDLE, ActivityState.ALERTING, None)

    # ── Listening ────────────────────────────────────────────
    elif current == ActivityState.LISTENING:
        # → Executing on intent_resolved
        if topic == Topics.VOICE_INTENT_DETECTED:
            intent = event.payload.get("intent", "")
            kind = resolve_executing_kind(intent)
            if kind:
                return (ActivityState.LISTENING, ActivityState.EXECUTING, kind)
            # intent 인식됐지만 kind 매핑 없으면 Idle 복귀
            return (ActivityState.LISTENING, ActivityState.IDLE, None)

        # → Idle on timeout_or_no_intent
        if topic == Topics.VOICE_INTENT_UNKNOWN:
            return (ActivityState.LISTENING, ActivityState.IDLE, None)
        if topic == Topics.VOICE_ACTIVITY_ENDED:
            return (ActivityState.LISTENING, ActivityState.IDLE, None)

        # → Alerting on timer_expired
        if topic == Topics.TIMER_EXPIRED:
            return (ActivityState.LISTENING, ActivityState.ALERTING, None)

    # ── Executing ────────────────────────────────────────────
    elif current == ActivityState.EXECUTING:
        # → Idle on action_done
        if topic == Topics.TASK_SUCCEEDED or topic == Topics.TASK_FAILED:
            return (ActivityState.EXECUTING, ActivityState.IDLE, None)

        # → Alerting on high_priority_alert (timer.expired)
        # 단, photo 중에는 defer (interrupts.py 에서 처리)
        if topic == Topics.TIMER_EXPIRED:
            # photo 중이면 defer – interrupts.py 에서 사전 차단해야 함
            if store.active_executing_kind != ExecutingKind.PHOTO:
                return (ActivityState.EXECUTING, ActivityState.ALERTING, None)

    # ── Alerting ─────────────────────────────────────────────
    elif current == ActivityState.ALERTING:
        # → Idle on acknowledged_or_timeout
        if topic in (Topics.TOUCH_TAP_DETECTED, Topics.TOUCH_STROKE_DETECTED):
            return (ActivityState.ALERTING, ActivityState.IDLE, None)
        # system.ack (payload 기반)
        if topic == Topics.VOICE_INTENT_DETECTED:
            intent = event.payload.get("intent", "")
            if intent == "system.ack":
                return (ActivityState.ALERTING, ActivityState.IDLE, None)

    return None
