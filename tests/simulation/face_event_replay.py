from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event


def build_face_event_replay(start: datetime | None = None) -> list[Event]:
    now = start or datetime.now(timezone.utc)
    return [
        Event.create(topics.VISION_FACE_DETECTED, "simulation.face", payload={"center": (0.5, 0.5)}, timestamp=now),
        Event.create(topics.VISION_FACE_MOVED, "simulation.face", payload={"center": (0.6, 0.5)}, timestamp=now + timedelta(milliseconds=200)),
        Event.create(topics.VISION_FACE_LOST, "simulation.face", timestamp=now + timedelta(seconds=3)),
        Event.create(topics.VISION_FACE_DETECTED, "simulation.face", payload={"center": (0.4, 0.5)}, timestamp=now + timedelta(seconds=8)),
    ]


if __name__ == "__main__":
    for event in build_face_event_replay():
        print(event)
