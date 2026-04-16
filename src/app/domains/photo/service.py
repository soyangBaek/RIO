"""Photo capture service.

Implements scenario VOICE-05: enter ``Executing(photo)`` → show a 3-second
countdown in the HUD → play shutter → call the camera adapter → save →
publish ``task.succeeded``. On cancel (POL-02 escape or scene preemption),
the in-flight countdown is cancelled and ``task.failed`` is emitted with a
``cancelled`` reason. The in-flight state is tracked explicitly so a
late-arriving shutter callback after cancel is ignored.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from ...adapters.display import Composition
from ...adapters.display.hud import clear_slot, set_countdown, SLOT_COUNTDOWN
from ...adapters.speaker import SFXPlayer
from ...core.events import topics
from ...core.events.models import Event, new_trace_id

_log = logging.getLogger(__name__)


CameraCapture = Callable[[], Optional[Path]]
Publisher = Callable[[Event], None]


class PhotoService:
    def __init__(
        self,
        publish: Publisher,
        sfx: SFXPlayer,
        composition: Composition,
        camera: Optional[CameraCapture] = None,
        countdown_s: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._publish = publish
        self._sfx = sfx
        self._composition = composition
        self._camera = camera
        self._countdown_s = max(1, countdown_s)
        self._clock = clock
        self._task_id_seq = 0
        self._current_task_id: Optional[str] = None
        self._timers: list[threading.Timer] = []

    # -- ExecutorHandler protocol ------------------------------------------
    def start(self, context: dict) -> None:
        self._cancel_timers()
        self._task_id_seq += 1
        task_id = f"photo_{self._task_id_seq}"
        self._current_task_id = task_id
        trace_id = context.get("trace_id") or new_trace_id()

        self._emit(topics.TASK_STARTED, {"task_id": task_id, "kind": "photo"}, trace_id)

        # Schedule HUD countdown updates plus the final shutter.
        for i, remaining in enumerate(range(self._countdown_s, 0, -1)):
            t = threading.Timer(i, self._show_countdown, args=(task_id, remaining))
            t.daemon = True
            self._timers.append(t)
            t.start()
        shutter_t = threading.Timer(
            self._countdown_s, self._fire_shutter, args=(task_id, trace_id)
        )
        shutter_t.daemon = True
        self._timers.append(shutter_t)
        shutter_t.start()

    def cancel(self) -> None:
        if self._current_task_id is None:
            return
        task_id = self._current_task_id
        self._current_task_id = None
        self._cancel_timers()
        clear_slot(self._composition, SLOT_COUNTDOWN)
        self._emit(
            topics.TASK_FAILED,
            {"task_id": task_id, "kind": "photo", "error": "cancelled"},
        )

    # -- internals ----------------------------------------------------------
    def _cancel_timers(self) -> None:
        for t in self._timers:
            t.cancel()
        self._timers.clear()

    def _show_countdown(self, task_id: str, number: int) -> None:
        if self._current_task_id != task_id:
            return
        set_countdown(self._composition, number)

    def _fire_shutter(self, task_id: str, trace_id: str) -> None:
        if self._current_task_id != task_id:
            return
        self._current_task_id = None
        clear_slot(self._composition, SLOT_COUNTDOWN)
        self._sfx.play("shutter")

        saved_path: Optional[Path] = None
        ok = True
        error: Optional[str] = None
        if self._camera is not None:
            try:
                saved_path = self._camera()
                if saved_path is None:
                    ok = False
                    error = "camera_returned_none"
            except Exception as e:  # pragma: no cover - hardware dependent
                _log.exception("camera capture raised")
                ok = False
                error = str(e)
        else:
            # No camera wired — common in dev; treat as successful dry run so
            # the scene can reach task.succeeded and light the happy oneshot.
            _log.info("photo service: no camera adapter, dry-run capture")

        payload = {"task_id": task_id, "kind": "photo"}
        if saved_path is not None:
            payload["result"] = str(saved_path)
        if ok:
            self._emit(topics.TASK_SUCCEEDED, payload, trace_id)
        else:
            payload["error"] = error or "unknown"
            self._emit(topics.TASK_FAILED, payload, trace_id)

    def _emit(self, topic: str, payload: dict, trace_id: Optional[str] = None) -> None:
        self._publish(
            Event(
                topic=topic,
                payload=payload,
                timestamp=self._clock(),
                trace_id=trace_id or new_trace_id(),
                source="photo",
            )
        )
