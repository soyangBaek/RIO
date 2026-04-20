from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Condition
from typing import Iterable

from src.app.core.events.models import Event


@dataclass(slots=True)
class PollBatch:
    events: list[Event]
    dropped: int = 0


class QueueBus:
    """A bounded in-process queue with drop-oldest overflow policy."""

    def __init__(self, maxsize: int = 256) -> None:
        self._queue: deque[Event] = deque()
        self._condition = Condition()
        self.maxsize = maxsize
        self.dropped_events = 0

    def publish(self, event: Event) -> None:
        with self._condition:
            if len(self._queue) >= self.maxsize:
                self._queue.popleft()
                self.dropped_events += 1
            self._queue.append(event)
            self._condition.notify()

    def publish_many(self, events: Iterable[Event]) -> None:
        for event in events:
            self.publish(event)

    def poll(self, timeout: float | None = None) -> Event | None:
        with self._condition:
            if not self._queue:
                self._condition.wait(timeout=timeout)
            if not self._queue:
                return None
            return self._queue.popleft()

    def drain(self) -> PollBatch:
        with self._condition:
            events = list(self._queue)
            self._queue.clear()
            dropped = self.dropped_events
            self.dropped_events = 0
            return PollBatch(events=events, dropped=dropped)
