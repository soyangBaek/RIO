"""Worker liveness monitor — emits ``system.degraded.entered`` on timeout.

Workers (``audio_worker``, ``vision_worker``) publish ``system.worker.heartbeat``
events on a regular cadence. This monitor keeps the last-seen timestamp per
worker and, when a worker stops reporting for longer than ``timeout_ms``,
publishes ``system.degraded.entered`` once so the rest of the system can fall
back to the capabilities that remain (scenarios ``OPS-06``, ``OPS-07``).

The monitor is polled: the main loop calls :meth:`tick` periodically (or on
every bus pump), and the check is cheap (O(#workers)). Recovery — a
previously-dead worker sending a heartbeat again — is also reported via a
:data:`RECOVERED_EVENT_TOPIC` hook so the safety layer can escalate or
clear flags, but the standard MVP only needs the "entered" direction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ..events import topics
from ..events.models import Event


# Maps a worker name to the capability tag the rest of the system uses to
# gate behaviour. Keep in sync with :func:`app.core.state.extended_state.
# apply_event` which reads ``lost_capability`` from the degraded event.
WORKER_TO_CAPABILITY: Dict[str, str] = {
    "audio_worker": "voice",
    "vision_worker": "vision",
}

Publisher = Callable[[Event], None]


@dataclass
class _WorkerSlot:
    last_beat_at: float
    degraded: bool = False


class HeartbeatMonitor:
    def __init__(
        self,
        publish: Publisher,
        timeout_ms: int = 5_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        self._publish = publish
        self._timeout_s = timeout_ms / 1000.0
        self._clock = clock
        self._slots: Dict[str, _WorkerSlot] = {}

    # -- subscription handler ----------------------------------------------
    def on_heartbeat(self, event: Event) -> None:
        """Router subscription entry for ``system.worker.heartbeat``."""
        if event.topic != topics.SYSTEM_WORKER_HEARTBEAT:
            return
        worker = event.payload.get("worker")
        if not isinstance(worker, str):
            return
        slot = self._slots.get(worker)
        if slot is None:
            self._slots[worker] = _WorkerSlot(last_beat_at=event.timestamp)
            return
        recovered = slot.degraded
        slot.last_beat_at = event.timestamp
        slot.degraded = False
        if recovered:
            # Optional: tell the rest of the system the worker is alive again.
            # We reuse the degraded topic with a ``recovered=True`` flag rather
            # than adding a new topic that architecture.md §6.3 does not list.
            self._publish(
                Event(
                    topic=topics.SYSTEM_DEGRADED_ENTERED,
                    payload={
                        "reason": f"{worker}_recovered",
                        "lost_capability": WORKER_TO_CAPABILITY.get(worker, worker),
                        "recovered": True,
                    },
                    timestamp=event.timestamp,
                    source="safety",
                )
            )

    # -- polling check ------------------------------------------------------
    def tick(self, now: Optional[float] = None) -> None:
        """Check each worker; emit ``system.degraded.entered`` on timeout."""
        current = now if now is not None else self._clock()
        for worker, slot in self._slots.items():
            if slot.degraded:
                continue
            if current - slot.last_beat_at >= self._timeout_s:
                slot.degraded = True
                self._publish(
                    Event(
                        topic=topics.SYSTEM_DEGRADED_ENTERED,
                        payload={
                            "reason": f"{worker}_heartbeat_lost",
                            "lost_capability": WORKER_TO_CAPABILITY.get(
                                worker, worker
                            ),
                        },
                        timestamp=current,
                        source="safety",
                    )
                )

    def is_degraded(self, worker: str) -> bool:
        slot = self._slots.get(worker)
        return slot is not None and slot.degraded

    def known_workers(self) -> Dict[str, float]:
        return {w: s.last_beat_at for w, s in self._slots.items()}
