from __future__ import annotations

from datetime import datetime, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event


def map_gesture_event(event: Event, *, now: datetime | None = None) -> list[Event]:
    if event.topic != topics.VISION_GESTURE_DETECTED:
        return []
    when = now or datetime.now(timezone.utc)
    gesture = event.payload.get("gesture")
    if gesture == "v_sign":
        return [
            Event.create(
                topics.VOICE_ACTIVITY_STARTED,
                "gesture.mapper",
                payload={"gesture": gesture, "synthetic": True},
                trace_id=event.trace_id,
                timestamp=when,
            ),
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "gesture.mapper",
                payload={"intent": "camera.capture", "gesture": gesture},
                trace_id=event.trace_id,
                timestamp=when,
            ),
            Event.create(
                topics.VOICE_ACTIVITY_ENDED,
                "gesture.mapper",
                payload={"gesture": gesture, "synthetic": True},
                trace_id=event.trace_id,
                timestamp=when,
            ),
        ]
    return []
