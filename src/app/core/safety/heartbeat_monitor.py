from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.app.core.events.models import Event
from src.app.core.events.topics import SYSTEM_DEGRADED_ENTERED, SYSTEM_WORKER_HEARTBEAT


@dataclass(slots=True)
class HeartbeatStatus:
    worker: str
    last_seen_at: datetime


class HeartbeatMonitor:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._heartbeats: dict[str, HeartbeatStatus] = {}

    def record(self, event: Event) -> None:
        worker = str(event.payload.get("worker", event.source))
        self._heartbeats[worker] = HeartbeatStatus(worker=worker, last_seen_at=event.timestamp)

    def check(self, now: datetime | None = None) -> list[Event]:
        current = now or datetime.now(timezone.utc)
        degraded: list[Event] = []
        for worker, status in list(self._heartbeats.items()):
            age = (current - status.last_seen_at).total_seconds()
            if age < self.timeout_seconds:
                continue
            lost_capability = "camera" if "vision" in worker else "microphone"
            degraded.append(
                Event.create(
                    SYSTEM_DEGRADED_ENTERED,
                    "heartbeat_monitor",
                    payload={"reason": "heartbeat_timeout", "lost_capability": lost_capability, "worker": worker},
                    timestamp=current,
                )
            )
        return degraded

    def heartbeat_event(self, worker: str, now: datetime | None = None) -> Event:
        return Event.create(
            SYSTEM_WORKER_HEARTBEAT,
            worker,
            payload={"worker": worker, "status": "ok"},
            timestamp=now or datetime.now(timezone.utc),
        )

