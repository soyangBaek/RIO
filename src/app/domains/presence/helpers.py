"""Derived presence situations (state-machine.md §3.1).

These helpers combine the FSM state and extended state into short-lived
boolean facts — ``is_searching_for_user``, ``recent_face_loss``,
``just_reappeared``. They are not states themselves, just query helpers.
"""
from __future__ import annotations

from ...core.state.models import Activity, ActivityKind, Context, ExtendedState
from . import signals

# Default thresholds come from ``configs/thresholds.yaml``; caller overrides.
DEFAULT_FACE_LOST_TIMEOUT_MS = 800
DEFAULT_WELCOME_MIN_AWAY_MS = 3_000


def is_searching_for_user(activity: Activity, ext: ExtendedState) -> bool:
    """Listening + no face currently visible → a search indicator is wanted."""
    return activity.kind is ActivityKind.LISTENING and not ext.face_present


def recent_face_loss(
    ext: ExtendedState,
    now: float,
    face_lost_timeout_ms: int = DEFAULT_FACE_LOST_TIMEOUT_MS,
) -> bool:
    """Face just vanished within the loss-latch window."""
    if ext.face_present:
        return False
    elapsed = signals.ms_since_face_seen(ext, now)
    return elapsed is not None and elapsed < face_lost_timeout_ms


def just_reappeared(
    old_context: Context,
    new_context: Context,
    ext: ExtendedState,
    now: float,
    welcome_min_away_ms: int = DEFAULT_WELCOME_MIN_AWAY_MS,
) -> bool:
    """Away/Sleepy → Idle after a long-enough absence (welcome gate)."""
    if old_context not in (Context.AWAY, Context.SLEEPY):
        return False
    if new_context is not Context.IDLE:
        return False
    elapsed = signals.ms_since_away_started(ext, now)
    return elapsed is not None and elapsed >= welcome_min_away_ms
