from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event


def build_long_scenario(start: datetime | None = None) -> list[Event]:
    now = start or datetime.now(timezone.utc)
    return [
        Event.create(topics.VISION_FACE_DETECTED, "simulation.long", payload={"center": (0.5, 0.5)}, timestamp=now),
        Event.create(topics.VOICE_ACTIVITY_STARTED, "simulation.long", timestamp=now + timedelta(seconds=1)),
        Event.create(
            topics.VOICE_INTENT_DETECTED,
            "simulation.long",
            payload={"intent": "weather.current", "text": "날씨 알려줘"},
            timestamp=now + timedelta(seconds=1, milliseconds=500),
        ),
        Event.create(topics.TASK_SUCCEEDED, "simulation.long", payload={"kind": "weather"}, timestamp=now + timedelta(seconds=2)),
        Event.create(topics.VISION_FACE_LOST, "simulation.long", timestamp=now + timedelta(minutes=4)),
        Event.create(topics.VISION_FACE_DETECTED, "simulation.long", payload={"center": (0.4, 0.5)}, timestamp=now + timedelta(minutes=5)),
    ]


if __name__ == "__main__":
    for event in build_long_scenario():
        print(event)
