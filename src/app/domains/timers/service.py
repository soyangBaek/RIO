"""Timer domain service.

Handles the ``timer.create`` intent (scenario VOICE-07):

- ``start(context)`` extracts the parsed ``duration_s`` slot from the intent
  payload, registers the timer with :class:`TimerScheduler`, tracks the
  label, and emits ``task.succeeded`` so :class:`ActivityFSM` returns to
  ``Idle`` right away. If parsing had failed (``duration_s`` missing), it
  emits ``task.failed`` with ``kind=timer_setup`` which triggers the
  confused oneshot (VOICE-08).
- Alert emission on expiry is the scheduler's job — it publishes
  ``timer.expired``, and the FSM routes the rest (Activity → Alerting,
  EffectPlanner → tone + TTS).

The service also keeps a small tracker of active timers so the HUD can
display the pending list.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from ...core.events import topics
from ...core.events.models import Event, new_trace_id
from ...core.scheduler import TimerScheduler

_log = logging.getLogger(__name__)
Publisher = Callable[[Event], None]


class TimerService:
    def __init__(
        self,
        publish: Publisher,
        scheduler: TimerScheduler,
    ) -> None:
        self._publish = publish
        self._scheduler = scheduler
        self._active: Dict[str, dict] = {}
        self._id_seq = 0

    # -- ExecutorHandler protocol ------------------------------------------
    def start(self, context: dict) -> None:
        payload = context.get("payload") or {}
        trace_id = context.get("trace_id") or new_trace_id()

        # ``duration_s`` is injected by the intent normalizer (T-039) after
        # timer_parser runs; a missing or non-positive value means parsing
        # failed or the STT missed the number.
        duration_s = payload.get("duration_s")
        try:
            duration_s = float(duration_s) if duration_s is not None else None
        except (TypeError, ValueError):
            duration_s = None

        if duration_s is None or duration_s <= 0:
            self._emit(
                topics.TASK_FAILED,
                {
                    "kind": "timer_setup",
                    "error": "no_duration",
                },
                trace_id,
            )
            return

        self._id_seq += 1
        timer_id = f"timer_{self._id_seq}"
        label = payload.get("label") or self._default_label(duration_s)

        self._active[timer_id] = {
            "label": label,
            "duration_s": duration_s,
        }
        self._scheduler.schedule(timer_id, duration_s, label=label)
        self._emit(
            topics.TASK_SUCCEEDED,
            {
                "kind": "timer_setup",
                "task_id": timer_id,
                "result": {
                    "timer_id": timer_id,
                    "duration_s": duration_s,
                    "label": label,
                },
            },
            trace_id,
        )

    def cancel(self) -> None:
        # Timer setup is instantaneous, so there is nothing to abort on a
        # cancel transition. Registered timers keep running — user intent
        # was to *schedule*, not to *babysit*.
        pass

    # -- housekeeping -------------------------------------------------------
    def on_timer_expired(self, event: Event) -> None:
        """Drop an entry once its timer has fired."""
        if event.topic != topics.TIMER_EXPIRED:
            return
        timer_id = event.payload.get("timer_id")
        if isinstance(timer_id, str):
            self._active.pop(timer_id, None)

    def active_timers(self) -> Dict[str, dict]:
        return dict(self._active)

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _default_label(duration_s: float) -> str:
        if duration_s >= 3600:
            return f"{int(duration_s // 3600)}시간"
        if duration_s >= 60:
            return f"{int(duration_s // 60)}분"
        return f"{int(duration_s)}초"

    def _emit(self, topic: str, payload: dict, trace_id: str) -> None:
        self._publish(
            Event(
                topic=topic,
                payload=payload,
                trace_id=trace_id,
                source="timers",
            )
        )
