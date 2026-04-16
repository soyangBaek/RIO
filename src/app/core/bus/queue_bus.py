"""Bounded multiprocessing event queue for the RIO event bus.

Workers (``audio_worker``, ``vision_worker``) publish events from their own
processes; the main orchestrator polls the queue in its event loop. The
channel is one-way — workers never consume their own events, and the main
process never publishes through this class (it uses in-process dispatch via
:mod:`app.core.bus.router`).

Capacity is bounded to prevent unbounded memory growth when a worker bursts
and the main loop is momentarily stalled. On overflow the **oldest** event
is dropped (not the newest): for real-time interaction freshness matters
more than history. Drop counts are tracked so :mod:`app.core.safety` can
surface persistent overflow as a degraded condition.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import queue as _stdqueue
from typing import List, Optional

from ..events.models import Event

_log = logging.getLogger(__name__)

DEFAULT_CAPACITY = 1024


class EventBus:
    """One-way bounded event channel between workers and the main process."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._queue: "mp.Queue[Event]" = mp.Queue(maxsize=capacity)
        self._dropped = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def dropped_count(self) -> int:
        return self._dropped

    def publish(self, event: Event) -> None:
        """Enqueue ``event``. Never blocks; drops the oldest on overflow."""
        try:
            self._queue.put_nowait(event)
            return
        except _stdqueue.Full:
            pass

        # Make room by dropping the oldest, then retry once.
        try:
            self._queue.get_nowait()
            self._dropped += 1
            _log.warning(
                "event bus full; dropped oldest (total drops=%d, capacity=%d)",
                self._dropped,
                self._capacity,
            )
        except _stdqueue.Empty:
            # A consumer drained between our put and get — just retry.
            pass

        try:
            self._queue.put_nowait(event)
        except _stdqueue.Full:
            # Another publisher refilled between drop and retry. Rather than
            # blocking the caller we drop the incoming event instead.
            self._dropped += 1
            _log.warning(
                "event bus still full after drop; discarded incoming %s",
                event.topic,
            )

    def poll(self, timeout: Optional[float] = None) -> Optional[Event]:
        """Return the next event or ``None`` if the queue is empty.

        ``timeout=None`` means non-blocking; positive values wait at most that
        many seconds for an event to arrive.

        Note on :class:`multiprocessing.Queue`: ``put`` schedules the item on
        an internal feeder thread that actually writes to the pipe, so a
        ``poll(timeout=None)`` issued in the same tick as ``publish`` may miss
        it. Main-loop callers already wait on other work between ticks, so a
        small timeout (~1 ms) is typically enough to cover the flush latency.
        """
        try:
            if timeout is None:
                return self._queue.get_nowait()
            return self._queue.get(timeout=timeout)
        except _stdqueue.Empty:
            return None

    def drain(self, max_items: int = 64) -> List[Event]:
        """Pull up to ``max_items`` pending events without blocking."""
        items: List[Event] = []
        for _ in range(max_items):
            try:
                items.append(self._queue.get_nowait())
            except _stdqueue.Empty:
                break
        return items

    def qsize_approx(self) -> int:
        """Best-effort queue size. Returns ``-1`` on platforms without qsize."""
        try:
            return self._queue.qsize()
        except NotImplementedError:
            return -1

    def close(self) -> None:
        self._queue.close()
        self._queue.join_thread()

    def mp_queue(self) -> "mp.Queue[Event]":
        """Return the underlying queue so worker processes can inherit it."""
        return self._queue
