from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class VisionInteractionTracker:
    left_threshold: float = 0.35
    right_threshold: float = 0.65
    direction_cooldown_ms: int = 1200
    peekaboo_timeout_ms: int = 2500
    _last_direction: str | None = field(default=None, init=False, repr=False)
    _last_direction_at: datetime | None = field(default=None, init=False, repr=False)
    _last_face_lost_at: datetime | None = field(default=None, init=False, repr=False)

    def on_face_lost(self, *, now: datetime | None = None) -> None:
        self._last_face_lost_at = now or datetime.now(timezone.utc)
        self._last_direction = None

    def on_face_detected(
        self,
        center: tuple[float, float],
        *,
        was_face_present: bool,
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        emitted: list[Event] = []

        if not was_face_present and self._last_face_lost_at is not None:
            age_ms = (when - self._last_face_lost_at).total_seconds() * 1000.0
            if 0 <= age_ms <= self.peekaboo_timeout_ms:
                emitted.append(
                    Event.create(
                        topics.VISION_GESTURE_DETECTED,
                        "vision.interaction_tracker",
                        payload={"gesture": "peekaboo", "confidence": 1.0},
                        confidence=1.0,
                        trace_id=trace_id,
                        timestamp=when,
                    )
                )

        direction: str | None = None
        if center[0] <= self.left_threshold:
            direction = "head_left"
        elif center[0] >= self.right_threshold:
            direction = "head_right"

        if direction is None:
            self._last_direction = None
            return emitted

        if self._last_direction == direction and self._last_direction_at is not None:
            age_ms = (when - self._last_direction_at).total_seconds() * 1000.0
            if age_ms < self.direction_cooldown_ms:
                return emitted

        self._last_direction = direction
        self._last_direction_at = when
        emitted.append(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "vision.interaction_tracker",
                payload={"gesture": direction, "confidence": 1.0},
                confidence=1.0,
                trace_id=trace_id,
                timestamp=when,
            )
        )
        return emitted
