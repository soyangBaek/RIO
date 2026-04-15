from __future__ import annotations

from collections.abc import Sequence

from src.app.adapters.touch.input import TouchSample
from src.app.core.events.models import Event
from src.app.core.events import topics


def classify_touch_sequence(samples: Sequence[TouchSample], stroke_threshold_px: int = 24) -> str:
    if len(samples) <= 1:
        return "tap"
    distance = abs(samples[-1].x - samples[0].x) + abs(samples[-1].y - samples[0].y)
    return "stroke" if distance >= stroke_threshold_px else "tap"


def map_touch_sequence(samples: Sequence[TouchSample], source: str = "touch") -> Event | None:
    if not samples:
        return None
    gesture = classify_touch_sequence(samples)
    if gesture == "stroke":
        return Event.create(
            topics.TOUCH_STROKE_DETECTED,
            source,
            payload={
                "path": [(sample.x, sample.y) for sample in samples],
                "duration_ms": int((samples[-1].timestamp - samples[0].timestamp).total_seconds() * 1000),
            },
            timestamp=samples[-1].timestamp,
        )
    return Event.create(
        topics.TOUCH_TAP_DETECTED,
        source,
        payload={"x": samples[-1].x, "y": samples[-1].y},
        timestamp=samples[-1].timestamp,
    )

