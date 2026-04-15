from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class FaceDetector:
    confidence_min: float = 0.6

    def detect(self, frame: Any, *, trace_id: str | None = None, now: datetime | None = None) -> Event | None:
        when = now or datetime.now(timezone.utc)
        if not isinstance(frame, dict):
            return None
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
