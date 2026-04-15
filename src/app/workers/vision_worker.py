from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.app.adapters.vision.camera_stream import CameraStream
from src.app.adapters.vision.face_detector import FaceDetector
from src.app.adapters.vision.face_tracker import FaceTracker
from src.app.adapters.vision.gesture_detector import GestureDetector
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.safety.heartbeat_monitor import HeartbeatMonitor


@dataclass(slots=True)
class VisionWorker:
    bus: QueueBus
    stream: CameraStream
    detector: FaceDetector
    tracker: FaceTracker
    gesture_detector: GestureDetector
    worker_name: str = "vision_worker"
    _face_present: bool = field(default=False, init=False, repr=False)

    def run_once(self, *, now: datetime | None = None) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        published: list[Event] = []
        frame = self.stream.read()
        detection = self.detector.detect(frame, now=when)
        if detection is not None:
            self._face_present = True
            self.bus.publish(detection)
            published.append(detection)
            center = tuple(detection.payload.get("center", (0.0, 0.0)))
            for event in self.tracker.update(center, now=when):
                self.bus.publish(event)
                published.append(event)
        elif self._face_present:
            self._face_present = False
            lost = Event.create(topics.VISION_FACE_LOST, "vision_worker", timestamp=when)
            self.bus.publish(lost)
            published.append(lost)

        for event in self.gesture_detector.detect(frame, now=when):
            self.bus.publish(event)
            published.append(event)

        heartbeat = HeartbeatMonitor().heartbeat_event(self.worker_name, now=when)
        self.bus.publish(heartbeat)
        published.append(heartbeat)
        return published
