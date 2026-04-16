"""Activity FSM — Idle / Listening / Executing(kind) / Alerting.

Authoritative spec: ``docs/state-machine.md`` §4. The function is pure —
interrupt policies (``domains/behavior/interrupts``) are expected to filter
events that should not reach this layer (photo lock, game/dance lock,
deferred_intent handling, etc. per §4.1). Here we implement only the base
transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..events import topics
from ..events.models import Event
from .models import Activity, ActivityKind, ExecutingKind, ExtendedState


# -- intent → executing kind mapping -----------------------------------------
_DIRECT_INTENT_KIND = {
    "camera.capture": ExecutingKind.PHOTO,
    "timer.create": ExecutingKind.TIMER_SETUP,
    "weather.current": ExecutingKind.WEATHER,
    "dance.start": ExecutingKind.DANCE,
    "ui.game_mode.enter": ExecutingKind.GAME,
}


def intent_to_executing_kind(intent: str) -> Optional[ExecutingKind]:
    """Map a canonical intent id to its :class:`ExecutingKind`.

    Returns ``None`` for intents that do not drive an Executing transition
    (``system.cancel``, ``system.ack``, and anything the FSM does not know).
    """
    if intent in _DIRECT_INTENT_KIND:
        return _DIRECT_INTENT_KIND[intent]
    if intent.startswith("smarthome."):
        return ExecutingKind.SMARTHOME
    return None


@dataclass(frozen=True)
class ActivityThresholds:
    """Timeouts that drive the Activity FSM."""
    listening_timeout_ms: int = 5_000          # Listening -> Idle when silent
    alerting_auto_timeout_ms: int = 30_000     # Alerting -> Idle without ack


_IDLE = Activity(ActivityKind.IDLE)
_LISTENING = Activity(ActivityKind.LISTENING)
_ALERTING = Activity(ActivityKind.ALERTING)


def transition(
    current: Activity,
    event: Event,
    ext: ExtendedState,
    now: float,
    thresholds: ActivityThresholds = ActivityThresholds(),
) -> Activity:
    """Return the next Activity, or ``current`` if no transition fires."""

    # -- high-priority system event: timer.expired -> Alerting ---------------
    # Photo lock is applied by the interrupt layer before we see this event,
    # so a ``timer.expired`` arriving here is allowed to preempt.
    if event.topic == topics.TIMER_EXPIRED and current.kind is not ActivityKind.ALERTING:
        return _ALERTING

    # -- voice.activity.started: Idle -> Listening ---------------------------
    if event.topic == topics.VOICE_ACTIVITY_STARTED:
        if current.kind is ActivityKind.IDLE:
            return _LISTENING
        return current  # Listening/Executing/Alerting: stay

    # -- voice.intent.detected: intent resolution ----------------------------
    if event.topic == topics.VOICE_INTENT_DETECTED:
        intent = event.payload.get("intent")
        if intent == "system.cancel":
            # Listening/Executing → Idle; Alerting → Idle (ack-like)
            if current.kind in (ActivityKind.LISTENING, ActivityKind.EXECUTING, ActivityKind.ALERTING):
                return _IDLE
            return current
        if intent == "system.ack":
            if current.kind is ActivityKind.ALERTING:
                return _IDLE
            return current  # ignore ack outside Alerting
        # Regular intent → Executing(kind) from Listening
        if current.kind is ActivityKind.LISTENING and isinstance(intent, str):
            kind = intent_to_executing_kind(intent)
            if kind is not None:
                return Activity(ActivityKind.EXECUTING, kind)
            # Unknown intent shape — no transition; caller may emit confused oneshot.
        return current

    # -- voice.intent.unknown: Listening -> Idle (confused handled elsewhere)-
    if event.topic == topics.VOICE_INTENT_UNKNOWN:
        if current.kind is ActivityKind.LISTENING:
            return _IDLE
        return current

    # -- task.succeeded / task.failed: Executing -> Idle --------------------
    if event.topic in (topics.TASK_SUCCEEDED, topics.TASK_FAILED):
        if current.kind is ActivityKind.EXECUTING:
            return _IDLE
        return current

    # -- time-driven tails (evaluated every tick) ---------------------------
    started_at = ext.activity_started_at
    if started_at is not None:
        elapsed_ms = (now - started_at) * 1000.0
        # Listening silence timeout → Idle
        if current.kind is ActivityKind.LISTENING and elapsed_ms >= thresholds.listening_timeout_ms:
            return _IDLE
        # Alerting safety timeout → Idle
        if current.kind is ActivityKind.ALERTING and elapsed_ms >= thresholds.alerting_auto_timeout_ms:
            return _IDLE

    return current
