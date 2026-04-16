"""Presence signal aggregation.

Reads the :class:`ExtendedState` and summarises *whether* the user is here
and *how recently* they engaged. The Context FSM (T-008) already uses these
signals; this module exposes them as plain helpers so adapters and scene
builders can query them without duplicating the thresholds.
"""
from __future__ import annotations

from typing import Optional

from ...core.state.models import ExtendedState


def has_any_evidence(ext: ExtendedState) -> bool:
    return ext.last_user_evidence_at is not None


def has_recent_evidence(ext: ExtendedState, now: float, window_ms: int) -> bool:
    ts = ext.last_user_evidence_at
    return ts is not None and (now - ts) * 1000.0 <= window_ms


def has_recent_interaction(ext: ExtendedState, now: float, window_ms: int) -> bool:
    ts = ext.last_interaction_at
    return ts is not None and (now - ts) * 1000.0 <= window_ms


def ms_since_face_seen(ext: ExtendedState, now: float) -> Optional[float]:
    if ext.last_face_seen_at is None:
        return None
    return max(0.0, (now - ext.last_face_seen_at) * 1000.0)


def ms_since_away_started(ext: ExtendedState, now: float) -> Optional[float]:
    if ext.away_started_at is None:
        return None
    return max(0.0, (now - ext.away_started_at) * 1000.0)


def is_confirmed_user(ext: ExtendedState, now: float, engagement_window_ms: int) -> bool:
    """``confirmed_user_and_interacting`` used by Context FSM."""
    return ext.face_present and has_recent_interaction(ext, now, engagement_window_ms)
