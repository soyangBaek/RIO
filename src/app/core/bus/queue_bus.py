from __future__ import annotations

import multiprocessing as mp
import queue
from dataclasses import dataclass
from typing import Iterable

from src.app.core.events.models import Event


@dataclass(slots=True)
class PollBatch:
    events: list[Event]
    dropped: int = 0


class QueueBus:
    """A bounded multiprocessing queue with drop-oldest overflow policy."""

    def __init__(self, maxsize: int = 256) -> None:
        self._queue: mp.Queue[Event] = mp.Queue(maxsize=maxsize)
        self.maxsize = maxsize
        self.dropped_events = 0

    def publish(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self.dropped_events += 1
            self._queue.put_nowait(event)

    def publish_many(self, events: Iterable[Event]) -> None:
        for event in events:
            self.publish(event)

    def poll(self, timeout: float | None = None) -> Event | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> PollBatch:
        events: list[Event] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return PollBatch(events=events, dropped=self.dropped_events)

