from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from src.app.core.events.models import Event
from src.app.core.events.topics import TIMER_EXPIRED
from src.app.core.state.models import TimerRecord


@dataclass(order=True)
class _ScheduledTimer:
    due_at: datetime
    timer_id: str = field(compare=False)
    label: str = field(compare=False)


class TimerScheduler:
    """Non-blocking timer registry driven by explicit polling."""

    def __init__(self) -> None:
        self._heap: list[_ScheduledTimer] = []
        self._timers: dict[str, TimerRecord] = {}

    def add_timer(
        self,
        delay_seconds: float,
        label: str = "",
        *,
        timer_id: str | None = None,
        now: datetime | None = None,
    ) -> TimerRecord:
        current = now or datetime.now(timezone.utc)
        record = TimerRecord(
            timer_id=timer_id or uuid4().hex,
            label=label,
            due_at=current + timedelta(seconds=delay_seconds),
            created_at=current,
            delay_seconds=delay_seconds,
        )
        self._timers[record.timer_id] = record
        heapq.heappush(self._heap, _ScheduledTimer(record.due_at, record.timer_id, label))
        return record

    def cancel_timer(self, timer_id: str) -> bool:
        return self._timers.pop(timer_id, None) is not None

    def poll_due(self, now: datetime | None = None) -> list[Event]:
        current = now or datetime.now(timezone.utc)
        due_events: list[Event] = []
        while self._heap and self._heap[0].due_at <= current:
            scheduled = heapq.heappop(self._heap)
            record = self._timers.pop(scheduled.timer_id, None)
            if record is None:
                continue
            due_events.append(
                Event.create(
                    TIMER_EXPIRED,
                    "scheduler",
                    payload={"timer_id": record.timer_id, "label": record.label},
                    timestamp=current,
                )
            )
        return due_events

    @property
    def timers(self) -> dict[str, TimerRecord]:
        return dict(self._timers)

