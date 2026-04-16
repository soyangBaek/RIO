"""Context FSM — Away / Idle / Engaged / Sleepy.

Authoritative spec: ``docs/state-machine.md`` §3. The transition function is a
pure function over ``(current, event, extended_state, now, thresholds)`` so
the reducer pipeline (T-012) can call it without side effects and the unit
tests (T-059) can drive it deterministically.

Per state-machine.md §9.1 the Context FSM does **not** read the Activity
state — the two axes are independent.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..events import topics
from ..events.models import Event
from .models import Context, ExtendedState

# Topics that constitute "user evidence" — any of them lifts Away to Idle.
EVIDENCE_TOPICS = frozenset({
    topics.VISION_FACE_DETECTED,
    topics.VISION_FACE_MOVED,
    topics.VOICE_ACTIVITY_STARTED,
    topics.VOICE_INTENT_DETECTED,
    topics.VOICE_INTENT_UNKNOWN,
    topics.TOUCH_TAP_DETECTED,
    topics.TOUCH_STROKE_DETECTED,
    topics.VISION_GESTURE_DETECTED,
})


@dataclass(frozen=True)
class ContextThresholds:
    """Time thresholds used by the Context FSM.

    Defaults follow ``configs/thresholds.yaml`` (state-machine.md is the spec).
    ``engaged_to_idle_timeout_ms`` and ``engagement_window_ms`` are not in the
    upstream YAML yet and are derived defaults documented here so they can be
    promoted later without changing call sites.
    """
    away_timeout_ms: int = 60_000          # no_face_long_timeout
    idle_to_sleepy_timeout_ms: int = 120_000  # long_idle
    engaged_to_idle_timeout_ms: int = 15_000  # no_interaction_for_a_while
    engagement_window_ms: int = 5_000      # interaction recency for Engaged


def transition(
    current: Context,
    event: Event,
    ext: ExtendedState,
    now: float,
    thresholds: ContextThresholds = ContextThresholds(),
) -> Context:
    """Return the next Context, or ``current`` if no transition fires.

    Pure: does not mutate ``ext``. Side-effects (e.g. setting
    ``away_started_at`` or emitting ``context.state.changed``) are owned by
    the reducer pipeline (T-012) which observes the change.
    """

    # 1. Sleepy -> Idle: gentle_wake (face only). Voice/touch alone in Sleepy
    #    are handled by the oneshot dispatcher (startled), not here.
    if current is Context.SLEEPY and event.topic == topics.VISION_FACE_DETECTED:
        return Context.IDLE

    # 2. Away -> Idle: any user evidence event.
    if current is Context.AWAY and event.topic in EVIDENCE_TOPICS:
        return Context.IDLE

    # 3. Idle -> Engaged: face_present AND recent interaction.
    if current is Context.IDLE and ext.face_present and ext.last_interaction_at is not None:
        elapsed_ms = (now - ext.last_interaction_at) * 1000.0
        if 0.0 <= elapsed_ms <= thresholds.engagement_window_ms:
            return Context.ENGAGED

    # -- time-driven transitions: evaluated on every event tick --

    # 4. Engaged -> Idle: no interaction for a while.
    if current is Context.ENGAGED and ext.last_interaction_at is not None:
        elapsed_ms = (now - ext.last_interaction_at) * 1000.0
        if elapsed_ms >= thresholds.engaged_to_idle_timeout_ms:
            # Demote, but Idle->Sleepy below may take precedence on the same tick.
            current = Context.IDLE

    # 5. Idle/Engaged -> Sleepy: long_idle.
    if current in (Context.IDLE, Context.ENGAGED):
        idle_since = ext.last_interaction_at or ext.last_user_evidence_at
        if idle_since is not None:
            elapsed_ms = (now - idle_since) * 1000.0
            if elapsed_ms >= thresholds.idle_to_sleepy_timeout_ms:
                return Context.SLEEPY

    # 6. Idle/Sleepy -> Away: no_face_long_timeout.
    if current in (Context.IDLE, Context.SLEEPY) and not ext.face_present:
        if ext.last_face_seen_at is not None:
            elapsed_ms = (now - ext.last_face_seen_at) * 1000.0
            if elapsed_ms >= thresholds.away_timeout_ms:
                return Context.AWAY

    return current
