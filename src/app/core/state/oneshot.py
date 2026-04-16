"""Oneshot dispatcher — transient emotional reactions that ride on top of
the FSM without changing it (state-machine.md §5).

Two concerns live here:

1. **Triggering**: mapping ``(event, old_context, new_context, extended_state)``
   to a :class:`OneshotName` candidate. This is the authoritative mapping for
   scenarios ``SYS-04``, ``SYS-09``, ``SYS-10a/b``, ``SYS-11``, ``VOICE-02``,
   ``VOICE-08``, ``INT-04``, ``INT-06b``, ``INT-07/08``.
2. **Dispatch (nesting policy)**: given an active oneshot and a new candidate,
   applying the ONE-01..ONE-05 rules — priority preemption, same-priority
   coalescing (≥80 % elapsed means replace, otherwise ignore), lower-priority
   drop, and no queueing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ..events import topics
from ..events.models import Event
from .models import (
    DEFAULT_ONESHOT_DURATION_MS,
    DEFAULT_ONESHOT_PRIORITY,
    Context,
    ExtendedState,
    Oneshot,
    OneshotName,
)


@dataclass(frozen=True)
class OneshotPolicy:
    """Tunable parameters for oneshots — priorities, durations, thresholds."""
    priorities: Dict[OneshotName, int] = field(
        default_factory=lambda: dict(DEFAULT_ONESHOT_PRIORITY)
    )
    durations_ms: Dict[OneshotName, int] = field(
        default_factory=lambda: dict(DEFAULT_ONESHOT_DURATION_MS)
    )
    # ONE-02 / ONE-03: same-priority candidate replaces the active oneshot
    # iff the active is past this fraction of its duration. State-machine §5.1
    # documents "80 %".
    coalesce_threshold: float = 0.8
    # "just_reappeared" gate for welcome (state-machine §3.1).
    welcome_min_away_ms: int = 3_000


def trigger_for_event(
    event: Event,
    old_context: Context,
    new_context: Context,
    ext: ExtendedState,
    now: float,
    policy: OneshotPolicy = OneshotPolicy(),
) -> Optional[OneshotName]:
    """Return the oneshot that should fire for this event, or ``None``.

    ``old_context`` / ``new_context`` are the Context values **before and
    after** :mod:`context_fsm` has run for this event, so welcome can detect
    a fresh Away/Sleepy → Idle transition.
    """

    # -- welcome: just_reappeared (Away/Sleepy -> Idle with long absence) ---
    if (
        new_context is Context.IDLE
        and old_context in (Context.AWAY, Context.SLEEPY)
        and ext.away_started_at is not None
    ):
        away_ms = (now - ext.away_started_at) * 1000.0
        if away_ms >= policy.welcome_min_away_ms:
            return OneshotName.WELCOME

    # -- startled: voice without face, or voice/touch in Sleepy w/o face ----
    if event.topic == topics.VOICE_ACTIVITY_STARTED and not ext.face_present:
        return OneshotName.STARTLED
    if (
        event.topic == topics.TOUCH_TAP_DETECTED
        and old_context is Context.SLEEPY
        and not ext.face_present
    ):
        # SYS-10b / INT-03c: sudden tap in Sleepy without a face is a surprise.
        return OneshotName.STARTLED

    # -- confused: intent parse failure --------------------------------------
    if event.topic == topics.VOICE_INTENT_UNKNOWN:
        return OneshotName.CONFUSED
    if event.topic == topics.TASK_FAILED:
        # Only timer_setup failure needs a confused expression (VOICE-08).
        # Weather/smarthome failures already surface their own feedback and
        # the scene selector runs Alert mood when appropriate.
        kind = event.payload.get("kind")
        if kind == "timer_setup":
            return OneshotName.CONFUSED

    # -- happy: petting stroke or a task success ----------------------------
    if event.topic == topics.TOUCH_STROKE_DETECTED:
        return OneshotName.HAPPY
    if event.topic == topics.TASK_SUCCEEDED:
        return OneshotName.HAPPY

    return None


def dispatch(
    active: Optional[Oneshot],
    candidate: OneshotName,
    now: float,
    policy: OneshotPolicy = OneshotPolicy(),
) -> Oneshot:
    """Apply the nesting rules and return the resulting active oneshot.

    The returned value may be ``candidate`` freshly started, the incumbent
    ``active`` (candidate dropped), or (same-priority + ≥threshold) a new
    instance of ``candidate``. Callers update the store with the return value.
    """
    cand_priority = policy.priorities[candidate]
    cand_duration = policy.durations_ms[candidate]
    fresh = Oneshot(candidate, cand_priority, cand_duration, now)

    if active is None or active.expired_at(now):
        return fresh

    if cand_priority > active.priority:
        return fresh  # ONE-01 preempt
    if cand_priority < active.priority:
        return active  # ONE-04 drop

    # ONE-02 / ONE-03: same priority
    if active.progress(now) >= policy.coalesce_threshold:
        return fresh
    return active


def expire_if_done(active: Optional[Oneshot], now: float) -> Optional[Oneshot]:
    """Clear the active oneshot if its duration has elapsed."""
    if active is None:
        return None
    if active.expired_at(now):
        return None
    return active
