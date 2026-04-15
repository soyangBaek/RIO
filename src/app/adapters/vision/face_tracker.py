from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class FaceTracker:
    sample_hz: float = 10.0
    _last_center: tuple[float, float] | None = field(default=None, init=False, repr=False)
    _last_emitted_at: datetime | None = field(default=None, init=False, repr=False)

    def update(
        self,
        center: tuple[float, float] | None,
        *,
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        if center is None:
            self._last_center = None
            return []
        if self._last_emitted_at is not None:
            interval = timedelta(seconds=1.0 / self.sample_hz)
            if when - self._last_emitted_at < interval:
                self._last_center = center
                return []
        self._last_center = center
        self._last_emitted_at = when
        return [
            Event.create(
                topics.VISION_FACE_MOVED,
                "vision.face_tracker",
                payload={"center": center},
                trace_id=trace_id,
                timestamp=when,
            )
        ]
