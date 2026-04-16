"""Timer scheduler — emits :data:`timer.expired` events on elapse.

The scheduler is thread-based so timers fire regardless of what the main
event loop is doing. Each firing posts a :class:`Event` through a caller-
provided ``publish`` callable. In normal operation that callable is the
:class:`EventBus` publisher so the event is enqueued and the main loop
picks it up on the next ``pump`` tick — that keeps every handler
(including FSM reducers) single-threaded.

Architecture notes:
- Timer lifecycle is entirely in-process; no scheduler runs inside the
  audio/vision workers.
- The scheduler publishes with ``source="scheduler"`` so downstream tracing
  can distinguish timer-driven events from worker-driven ones.
- Registered ids must be unique; a ``schedule`` call with an existing id
  cancels the previous timer and replaces it (matches "latest wins" for
  voice-commanded timer overrides).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from ..events import topics
from ..events.models import Event


Publisher = Callable[[Event], None]


class TimerScheduler:
    def __init__(
        self,
        publish: Publisher,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._publish = publish
        self._clock = clock
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(
        self,
        timer_id: str,
        duration_s: float,
        label: Optional[str] = None,
    ) -> None:
        """Register (or replace) a timer by id. Fires after ``duration_s``."""
        if duration_s < 0:
            raise ValueError("duration_s must be non-negative")
        self.cancel(timer_id)

        def _fire() -> None:
            event = Event(
                topic=topics.TIMER_EXPIRED,
                payload={"timer_id": timer_id, "label": label},
                timestamp=self._clock(),
                source="scheduler",
            )
            try:
                self._publish(event)
            finally:
                with self._lock:
                    self._timers.pop(timer_id, None)

        t = threading.Timer(duration_s, _fire)
        t.daemon = True
        with self._lock:
            self._timers[timer_id] = t
        t.start()

    def cancel(self, timer_id: str) -> bool:
        """Cancel an active timer. Returns ``True`` if one was pending."""
        with self._lock:
            t = self._timers.pop(timer_id, None)
        if t is not None:
            t.cancel()
            return True
        return False

    def active_ids(self) -> List[str]:
        with self._lock:
            return list(self._timers.keys())

    def shutdown(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for t in timers:
            t.cancel()
