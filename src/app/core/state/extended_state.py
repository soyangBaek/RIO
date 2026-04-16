"""Extended-state updates for the RIO state machine.

State-machine.md §3.1 lists the non-FSM fields the system needs to interpret
the FSM and derive scenes — timestamps, the presence flag, and the
``deferred_intent`` slot. This module owns the **first** step of the reducer
pipeline (architecture.md §4 step 2): mapping a raw input event to a
:class:`ExtendedState` mutation. FSM transitions and oneshot dispatch run
*after* this update reads the refreshed timestamps.

Scope
-----
- Updates ``face_present`` and the four ``*_at`` timestamps from bus events.
- Updates ``capabilities`` in response to ``system.degraded.entered``.

Out of scope (lives elsewhere by design):
- ``away_started_at`` is set by the Context FSM transition into ``AWAY``
  (see :mod:`reducers`); we only initialise it on cold start.
- ``active_executing_kind`` is set by the Activity FSM (``executing_kind``
  helpers in this module are exposed for that reducer to call).
- ``deferred_intent`` is owned by ``domains/behavior/interrupts``.
- ``timers``, ``inflight_requests`` are owned by their domain services.
"""
from __future__ import annotations

from typing import Optional

from ..events.models import Event
from ..events import topics
from .models import ExecutingKind, ExtendedState


def apply_event(state: ExtendedState, event: Event) -> None:
    """Update timestamp/presence fields based on an inbound bus ``event``.

    Called once per event before the FSM reducers run. Unknown topics are
    silently ignored — the FSMs and oneshot dispatcher will see them next.
    """
    topic = event.topic
    ts = event.timestamp

    # -- vision -------------------------------------------------------------
    if topic == topics.VISION_FACE_DETECTED:
        state.face_present = True
        state.last_face_seen_at = ts
        state.last_user_evidence_at = ts
        return
    if topic == topics.VISION_FACE_MOVED:
        # Continuing presence: refresh face/evidence stamps but do not count
        # as an interaction (no voice/touch/gesture intent).
        state.face_present = True
        state.last_face_seen_at = ts
        state.last_user_evidence_at = ts
        return
    if topic == topics.VISION_FACE_LOST:
        state.face_present = False
        payload_last = event.payload.get("last_seen_at")
        if isinstance(payload_last, (int, float)):
            state.last_face_seen_at = float(payload_last)
        # Otherwise keep the previous last_face_seen_at unchanged.
        return
    if topic == topics.VISION_GESTURE_DETECTED:
        state.last_user_evidence_at = ts
        state.last_interaction_at = ts
        return

    # -- voice --------------------------------------------------------------
    if topic == topics.VOICE_ACTIVITY_STARTED:
        # Voice presence is evidence even before STT resolves the intent.
        state.last_user_evidence_at = ts
        return
    if topic in (topics.VOICE_INTENT_DETECTED, topics.VOICE_INTENT_UNKNOWN):
        state.last_user_evidence_at = ts
        state.last_interaction_at = ts
        return
    # voice.activity.ended carries no presence/interaction signal on its own.

    # -- touch --------------------------------------------------------------
    if topic in (topics.TOUCH_TAP_DETECTED, topics.TOUCH_STROKE_DETECTED):
        state.last_user_evidence_at = ts
        state.last_interaction_at = ts
        return

    # -- system / safety ----------------------------------------------------
    if topic == topics.SYSTEM_DEGRADED_ENTERED:
        cap = event.payload.get("lost_capability")
        if isinstance(cap, str):
            state.capabilities[cap] = False
            # OPS-06: vision loss forces face_present false so downstream
            # derived situations stop assuming a tracked face.
            if cap == "vision":
                state.face_present = False
        return


# -- helpers used by reducers / safety subsystems ---------------------------
def set_capability(state: ExtendedState, name: str, available: bool) -> None:
    state.capabilities[name] = available


def mark_away_start(state: ExtendedState, ts: float) -> None:
    state.away_started_at = ts


def clear_away_start(state: ExtendedState) -> None:
    state.away_started_at = None


def set_executing_kind(state: ExtendedState, kind: Optional[ExecutingKind]) -> None:
    state.active_executing_kind = kind


def reset_face_presence(state: ExtendedState) -> None:
    """Force ``face_present`` to ``False`` (used by heartbeat-loss handling)."""
    state.face_present = False
