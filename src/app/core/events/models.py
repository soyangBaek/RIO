"""Common event envelope shared across workers and the main orchestrator.

Every signal on the RIO bus — face detection, VAD activation, touch taps,
timer expiry, heartbeat pings — travels as an :class:`Event`. Consumers route
on ``topic`` (see ``core/events/topics.py``) and use ``trace_id`` to correlate
chains of related events across the audio worker, vision worker, and main
process.

Timestamps use :func:`time.monotonic` so comparisons remain stable across
wall-clock adjustments (NTP, DST). On Linux this clock is system-wide, so
values produced in separate worker processes are directly comparable.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping


def new_trace_id() -> str:
    """Return a fresh trace id for a new event chain."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Event:
    topic: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)
    trace_id: str = field(default_factory=new_trace_id)
    source: str = "main"
