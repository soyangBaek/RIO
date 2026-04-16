from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class FaceDetector:
    confidence_min: float = 0.6
    _detector: Any = field(default=None, init=False, repr=False)

    def _ensure_detector(self) -> Any:
        if self._detector is not None:
            return self._detector
        import mediapipe as mp

        self._detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=self.confidence_min,
        )
        return self._detector

    def detect(self, frame: Any, *, trace_id: str | None = None, now: datetime | None = None) -> Event | None:
        when = now or datetime.now(timezone.utc)
        if not isinstance(frame, dict):
            detector = self._ensure_detector()
            import cv2

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = detector.process(rgb)
            if not result.detections:
                return None
            detection = result.detections[0]
            box = detection.location_data.relative_bounding_box
            center = (
                float(box.xmin + box.width / 2.0),
                float(box.ymin + box.height / 2.0),
            )
            confidence = float(detection.score[0]) if detection.score else 0.0
            if confidence < self.confidence_min:
                return None
            return Event.create(
                topics.VISION_FACE_DETECTED,
                "vision.face_detector",
                payload={"center": center, "confidence": confidence},
                confidence=confidence,
                trace_id=trace_id,
                timestamp=when,
            )
        center = frame.get("face_center")
        confidence = float(frame.get("face_confidence", 0.0))
        if center is None or confidence < self.confidence_min:
            return None
        return Event.create(
            topics.VISION_FACE_DETECTED,
            "vision.face_detector",
            payload={"center": tuple(center), "confidence": confidence},
            confidence=confidence,
            trace_id=trace_id,
            timestamp=when,
        )
