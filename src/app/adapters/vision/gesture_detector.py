from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class GestureDetector:
    confidence_min: float = 0.75

    def detect(self, frame: Any, *, trace_id: str | None = None, now: datetime | None = None) -> list[Event]:
        if not isinstance(frame, dict):
            return []
        when = now or datetime.now(timezone.utc)
        gesture = frame.get("gesture")
        confidence = float(frame.get("gesture_confidence", 0.0))
        if gesture and confidence >= self.confidence_min:
            return [
                Event.create(
                    topics.VISION_GESTURE_DETECTED,
                    "vision.gesture_detector",
                    payload={"gesture": gesture, "confidence": confidence},
                    confidence=confidence,
                    trace_id=trace_id,
                    timestamp=when,
                )
            ]
        return []
