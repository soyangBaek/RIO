"""Activity-level interrupt policies (state-machine.md §4.1, scenarios POL-*).

The main loop consults :class:`InterruptGate` **before** handing an event to
the FSM reducer. The gate decides whether the event:

* :data:`Decision.ALLOW` — proceeds normally.
* :data:`Decision.DROP` — ignored (e.g., new intent during photo).
* :data:`Decision.DEFER` — stashed in ``extended_state.deferred_intent``
  for replay after the current Executing finishes (POL-04 / POL-05).

Design choices:

- The gate is stateless; deferred-intent storage lives in
  :class:`ExtendedState` so it follows the single source of truth.
- ``system.cancel`` and ``system.ack`` are always allowed so a user can
  always escape the current activity.
- ``timer.expired`` is the only MVP high-priority alert. During
  ``Executing(photo)`` it is deferred (POL-03); in game/dance it passes
  through (POL-06).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ...core.events import topics
from ...core.events.models import Event
from ...core.state.models import Activity, ActivityKind, ExecutingKind, ExtendedState


class Decision(Enum):
    ALLOW = "allow"
    DROP = "drop"
    DEFER = "defer"


# Intents that always pass (scenarios POL-02, POL-06, VOICE-15, VOICE-16).
_ALWAYS_ALLOWED_INTENTS = frozenset({"system.cancel", "system.ack"})

# Executing kinds that may enqueue a single deferred intent on interruption
# (POL-04). Photo/game/dance use different (stricter) policies.
_DEFERRABLE_KINDS = frozenset({
    ExecutingKind.SMARTHOME,
    ExecutingKind.WEATHER,
    ExecutingKind.TIMER_SETUP,
})


@dataclass(frozen=True)
class InterruptGate:
    """Stateless decision function. Instantiate once, share widely."""

    def decide(self, activity: Activity, event: Event) -> Decision:
        topic = event.topic
        intent = (
            event.payload.get("intent")
            if topic == topics.VOICE_INTENT_DETECTED
            else None
        )

        # Always allow escape hatches.
        if intent in _ALWAYS_ALLOWED_INTENTS:
            return Decision.ALLOW

        if activity.kind is not ActivityKind.EXECUTING:
            # Idle / Listening / Alerting → normal rules apply. The FSM
            # itself enforces ``system.ack`` only inside Alerting and the
            # listening timeout etc.; we do not gate them here.
            return Decision.ALLOW

        kind = activity.executing
        assert kind is not None  # guaranteed by Activity.__post_init__

        # -- Executing(photo): strict lock --------------------------------
        if kind is ExecutingKind.PHOTO:
            if topic == topics.TIMER_EXPIRED:
                return Decision.DEFER  # POL-03
            if topic == topics.VOICE_INTENT_DETECTED:
                return Decision.DROP  # POL-02
            return Decision.ALLOW

        # -- Executing(game|dance): locked except cancel / timer expiry --
        if kind in (ExecutingKind.GAME, ExecutingKind.DANCE):
            if topic == topics.TIMER_EXPIRED:
                return Decision.ALLOW  # high_priority_alert (POL-06)
            if topic == topics.VOICE_INTENT_DETECTED:
                return Decision.DROP
            return Decision.ALLOW

        # -- Executing(smarthome|weather|timer_setup): defer new intents --
        if kind in _DEFERRABLE_KINDS:
            if topic == topics.VOICE_INTENT_DETECTED:
                return Decision.DEFER
            return Decision.ALLOW

        return Decision.ALLOW


def store_deferred(ext: ExtendedState, event: Event) -> None:
    """Overwrite ``deferred_intent`` with the latest pending intent (POL-04)."""
    ext.deferred_intent = {
        "topic": event.topic,
        "payload": dict(event.payload),
        "timestamp": event.timestamp,
        "trace_id": event.trace_id,
        "source": event.source,
    }


def pop_deferred(ext: ExtendedState) -> Optional[Event]:
    """Pull and clear the deferred intent. Returns the re-materialised Event."""
    data = ext.deferred_intent
    if data is None:
        return None
    ext.deferred_intent = None
    return Event(
        topic=data["topic"],
        payload=data.get("payload") or {},
        timestamp=data["timestamp"],
        trace_id=data["trace_id"],
        source=data.get("source", "main"),
    )
