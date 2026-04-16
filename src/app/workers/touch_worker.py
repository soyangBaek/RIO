from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.app.adapters.touch.gesture_mapper import map_touch_sequence
from src.app.adapters.touch.input import TouchInputAdapter, TouchSample
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.safety.heartbeat_monitor import HeartbeatMonitor


@dataclass(slots=True)
class TouchWorker:
    bus: QueueBus
    adapter: TouchInputAdapter
    worker_name: str = "touch_worker"
    max_batch_size: int = 32

    def run_once(self, *, now: datetime | None = None) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        published: list[Event] = []
        samples: list[TouchSample] = []
        while len(samples) < self.max_batch_size:
            sample = self.adapter.read()
            if sample is None:
                break
            samples.append(sample)

        touch_event = map_touch_sequence(samples, source=self.worker_name)
        if touch_event is not None:
            self.bus.publish(touch_event)
            published.append(touch_event)

        heartbeat = HeartbeatMonitor().heartbeat_event(self.worker_name, now=when)
        self.bus.publish(heartbeat)
        published.append(heartbeat)
        return published
