"""Face event replayer — inject ``vision.face.*`` events with monotonic
timestamps into an :class:`EventBus` / publisher so scenarios run without
a camera.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.events import Event, topics  # noqa: E402


def face_detected(ts: float, center: Tuple[float, float] = (0.5, 0.5),
                  confidence: float = 0.9) -> Event:
    return Event(
        topic=topics.VISION_FACE_DETECTED,
        payload={
            "bbox": [center[0] - 0.1, center[1] - 0.1, 0.2, 0.2],
            "center": list(center),
            "confidence": confidence,
        },
        timestamp=ts,
        source="face_event_replay",
    )


def face_moved(ts: float, center: Tuple[float, float]) -> Event:
    return Event(
        topic=topics.VISION_FACE_MOVED,
        payload={"center": list(center), "delta": [0.0, 0.0]},
        timestamp=ts,
        source="face_event_replay",
    )


def face_lost(ts: float, last_seen_at: Optional[float] = None) -> Event:
    payload = {}
    if last_seen_at is not None:
        payload["last_seen_at"] = last_seen_at
    return Event(
        topic=topics.VISION_FACE_LOST,
        payload=payload,
        timestamp=ts,
        source="face_event_replay",
    )


def replay(events: Iterable[Event], publish: Callable[[Event], None]) -> int:
    count = 0
    for e in events:
        publish(e)
        count += 1
    return count


def test_replay_basic():
    emitted = []
    n = replay(
        [face_detected(1.0), face_moved(1.1, (0.6, 0.5)), face_lost(2.0)],
        emitted.append,
    )
    assert n == 3
    assert emitted[0].topic == topics.VISION_FACE_DETECTED
    assert emitted[1].topic == topics.VISION_FACE_MOVED
    assert emitted[2].topic == topics.VISION_FACE_LOST


if __name__ == "__main__":
    test_replay_basic()
    print("ok: face_event_replay self-test")
