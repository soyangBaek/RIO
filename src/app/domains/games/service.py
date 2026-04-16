"""Games service.

MVP only supports entering / leaving game mode UI. Actual game content
(rock-paper-scissors, hide-and-seek, etc.) is Phase 2. When the Activity
FSM enters ``Executing(game)``, ``start`` publishes ``task.started`` and
stays idle until the user cancels or Phase 2 wires in real game logic;
``cancel`` emits ``task.succeeded`` (the user simply exits the mode).
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from ...core.events import topics
from ...core.events.models import Event, new_trace_id

_log = logging.getLogger(__name__)
Publisher = Callable[[Event], None]


class GamesService:
    def __init__(self, publish: Publisher) -> None:
        self._publish = publish
        self._task_seq = 0
        self._active_task: str | None = None
        self._trace: str | None = None

    def start(self, context: dict) -> None:
        self._task_seq += 1
        self._active_task = f"game_{self._task_seq}"
        self._trace = context.get("trace_id") or new_trace_id()
        self._emit(topics.TASK_STARTED, {
            "task_id": self._active_task,
            "kind": "game",
        })

    def cancel(self) -> None:
        if self._active_task is None:
            return
        task_id = self._active_task
        self._active_task = None
        self._emit(topics.TASK_SUCCEEDED, {
            "task_id": task_id,
            "kind": "game",
            "result": {"exited": True},
        })
        self._trace = None

    def _emit(self, topic: str, payload: dict) -> None:
        self._publish(
            Event(
                topic=topic,
                payload=payload,
                timestamp=time.monotonic(),
                trace_id=self._trace or new_trace_id(),
                source="games",
            )
        )
