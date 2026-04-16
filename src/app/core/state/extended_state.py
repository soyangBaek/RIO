from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from src.app.core.events.models import Event
from src.app.core.events import topics
from src.app.core.state.models import ActionKind, CapabilityState, ContextState, ExtendedState


USER_EVIDENCE_TOPICS = {
    topics.VISION_FACE_DETECTED,
    topics.VOICE_ACTIVITY_STARTED,
    topics.TOUCH_TAP_DETECTED,
    topics.TOUCH_STROKE_DETECTED,
}

INTERACTION_TOPICS = {
    topics.VOICE_ACTIVITY_STARTED,
    topics.VOICE_INTENT_DETECTED,
    topics.TOUCH_TAP_DETECTED,
    topics.TOUCH_STROKE_DETECTED,
    topics.VISION_GESTURE_DETECTED,
}


def apply_extended_state(
    extended: ExtendedState,
    event: Event,
    *,
    now: datetime | None = None,
) -> ExtendedState:
    current = deepcopy(extended)
    when = now or event.timestamp

    if event.topic == topics.VISION_FACE_DETECTED:
        current.face_present = True
        current.last_face_seen_at = when
    elif event.topic == topics.VISION_FACE_LOST:
        current.face_present = False
        current.last_face_lost_at = when
    elif event.topic == topics.TASK_STARTED:
        task_id = str(event.payload.get("task_id", "unknown"))
        current.inflight_requests[task_id] = dict(event.payload)
    elif event.topic in {topics.TASK_SUCCEEDED, topics.TASK_FAILED}:
        task_id = str(event.payload.get("task_id", "unknown"))
        current.inflight_requests.pop(task_id, None)
        if event.payload.get("clear_ui_mode"):
            current.ui_mode = None
        elif event.payload.get("ui_mode"):
            current.ui_mode = str(event.payload.get("ui_mode"))
    elif event.topic == topics.ACTIVITY_STATE_CHANGED:
        if event.payload.get("to") == "Executing":
            kind = event.payload.get("kind")
            current.active_executing_kind = ActionKind(kind) if kind else None
        else:
            current.active_executing_kind = None
    elif event.topic == topics.CONTEXT_STATE_CHANGED:
        previous = event.payload.get("from")
        if previous:
            current.previous_context_state = ContextState(previous)
        if event.payload.get("to") in {"Away", "Sleepy"}:
            current.away_started_at = when
    elif event.topic == topics.SYSTEM_DEGRADED_ENTERED:
        lost = event.payload.get("lost_capability")
        if lost == "camera":
            current.capabilities.camera_available = False
            current.face_present = False
        elif lost == "microphone":
            current.capabilities.mic_available = False
        elif lost == "touch":
            current.capabilities.touch_available = False
        elif lost == "speaker":
            current.capabilities.speaker_available = False
    elif event.topic == topics.VOICE_INTENT_DETECTED and event.payload.get("intent") == "system.cancel":
        current.ui_mode = None

    if event.topic in USER_EVIDENCE_TOPICS or event.topic == topics.VOICE_INTENT_DETECTED:
        current.last_user_evidence_at = when
    if event.topic in INTERACTION_TOPICS:
        current.last_interaction_at = when

    return current


def set_deferred_intent(extended: ExtendedState, payload: dict[str, Any] | None) -> ExtendedState:
    current = deepcopy(extended)
    current.deferred_intent = deepcopy(payload) if payload else None
    return current


def set_capabilities(extended: ExtendedState, capabilities: CapabilityState) -> ExtendedState:
    current = deepcopy(extended)
    current.capabilities = deepcopy(capabilities)
    return current
