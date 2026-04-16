"""Integration test — voice intent → executing → idle full flow.

Exercises the Router / Reducer / Executor wiring without spinning up worker
processes (workers are replaced by direct event injection).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.bus import Router  # noqa: E402
from app.core.events import Event, topics  # noqa: E402
from app.core.state import ActivityKind, ExecutingKind, StateStore  # noqa: E402
from app.core.state.reducers import Reducer  # noqa: E402
from app.domains.behavior import ExecutorRegistry  # noqa: E402


class RecordingHandler:
    def __init__(self):
        self.starts = []
        self.cancels = 0

    def start(self, context):
        self.starts.append(context)

    def cancel(self):
        self.cancels += 1


def test_voice_started_then_camera_capture_succeeds():
    store = StateStore()
    router = Router()
    reducer = Reducer(store, router)
    executors = ExecutorRegistry()

    photo = RecordingHandler()
    executors.register(ExecutingKind.PHOTO, photo)
    router.subscribe(topics.ACTIVITY_STATE_CHANGED, executors.on_activity_changed)

    # face appears → idle
    reducer.reduce(
        Event(topic=topics.VISION_FACE_DETECTED, timestamp=1.0,
              payload={"bbox": [0.3, 0.3, 0.4, 0.4], "center": [0.5, 0.5], "confidence": 0.9})
    )
    # voice started → listening
    reducer.reduce(Event(topic=topics.VOICE_ACTIVITY_STARTED, timestamp=2.0))
    assert store.get().activity.kind is ActivityKind.LISTENING

    # intent detected → executing(photo) → executor.start invoked
    reducer.reduce(
        Event(topic=topics.VOICE_INTENT_DETECTED, timestamp=2.5,
              payload={"intent": "camera.capture", "confidence": 0.92, "text": "사진 찍어줘"})
    )
    assert store.get().activity.kind is ActivityKind.EXECUTING
    assert store.get().activity.executing is ExecutingKind.PHOTO
    assert len(photo.starts) == 1

    # task.succeeded → idle + cancel notification to executor
    reducer.reduce(
        Event(topic=topics.TASK_SUCCEEDED, timestamp=5.0,
              payload={"task_id": "photo_1", "kind": "photo"})
    )
    assert store.get().activity.kind is ActivityKind.IDLE
    assert photo.cancels == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
