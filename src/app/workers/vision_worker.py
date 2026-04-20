from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.app.adapters.vision.camera_stream import CameraStream
from src.app.adapters.vision.face_detector import FaceDetector
from src.app.adapters.vision.face_tracker import FaceTracker
from src.app.adapters.vision.gesture_detector import GestureDetector
from src.app.adapters.vision.interaction_tracker import VisionInteractionTracker
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.safety.heartbeat_monitor import HeartbeatMonitor
from src.app.core.safety.tick_metrics import record as record_metric


@dataclass(slots=True)
class VisionWorker:
    bus: QueueBus
    stream: CameraStream
    detector: FaceDetector
    tracker: FaceTracker
    gesture_detector: GestureDetector
    interaction_tracker: VisionInteractionTracker = field(default_factory=VisionInteractionTracker)
    worker_name: str = "vision_worker"
    _face_present: bool = field(default=False, init=False, repr=False)
    last_frame: object | None = field(default=None, init=False, repr=False)
    last_face_event: Event | None = field(default=None, init=False, repr=False)
    last_gesture: str | None = field(default=None, init=False, repr=False)
    last_frame_loop_ms: float = field(default=0.0, init=False, repr=False)
    last_face_detect_ms: float = field(default=0.0, init=False, repr=False)
    last_gesture_detect_ms: float = field(default=0.0, init=False, repr=False)

    def run_once(self, *, now: datetime | None = None) -> list[Event]:
        started_at = time.perf_counter()
        when = now or datetime.now(timezone.utc)
        published: list[Event] = []
        frame = self.stream.read()
        self.last_frame = frame
        rgb_frame = None
        if not isinstance(frame, dict):
            import cv2

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        face_started_at = time.perf_counter()
        detection = self.detector.detect(frame, now=when, rgb_frame=rgb_frame)
        self.last_face_detect_ms = (time.perf_counter() - face_started_at) * 1000.0
        self.last_face_event = detection
        if detection is not None:
            was_face_present = self._face_present
            self._face_present = True
            self.bus.publish(detection)
            published.append(detection)
            center = tuple(detection.payload.get("center", (0.0, 0.0)))
            for event in self.tracker.update(center, now=when):
                self.bus.publish(event)
                published.append(event)
            for event in self.interaction_tracker.on_face_detected(
                center,
                was_face_present=was_face_present,
                trace_id=detection.trace_id,
                now=when,
            ):
                self.bus.publish(event)
                published.append(event)
        elif self._face_present:
            self._face_present = False
            self.interaction_tracker.on_face_lost(now=when)
            lost = Event.create(topics.VISION_FACE_LOST, "vision_worker", timestamp=when)
            self.bus.publish(lost)
            published.append(lost)

        gesture_started_at = time.perf_counter()
        gestures = self.gesture_detector.detect(frame, now=when, rgb_frame=rgb_frame)
        self.last_gesture_detect_ms = (time.perf_counter() - gesture_started_at) * 1000.0
        self.last_gesture = None
        for event in gestures:
            self.bus.publish(event)
            published.append(event)
            self.last_gesture = str(event.payload.get("gesture") or self.last_gesture)

        heartbeat = HeartbeatMonitor().heartbeat_event(self.worker_name, now=when)
        self.bus.publish(heartbeat)
        published.append(heartbeat)
        frame_loop_ms = (time.perf_counter() - started_at) * 1000.0
        self.last_frame_loop_ms = frame_loop_ms
        record_metric("frame_loop_ms", frame_loop_ms)
        return published
