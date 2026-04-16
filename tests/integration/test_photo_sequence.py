"""Photo service integration — countdown, shutter, cancel, interrupt."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.adapters.display import Composition  # noqa: E402
from app.adapters.display.hud import SLOT_COUNTDOWN  # noqa: E402
from app.core.events import Event, topics  # noqa: E402
from app.domains.behavior import Decision, InterruptGate  # noqa: E402
from app.domains.photo import PhotoService  # noqa: E402
from app.core.state import Activity, ActivityKind, ExecutingKind  # noqa: E402


class SpySFX:
    def __init__(self):
        self.calls = []
    def play(self, slot):
        self.calls.append(slot); return True
    def stop_all(self):
        pass


def test_countdown_shutter_success():
    sfx = SpySFX()
    comp = Composition()
    captured = []
    service = PhotoService(
        publish=lambda e: captured.append(e),
        sfx=sfx,
        composition=comp,
        camera=lambda: Path("/tmp/rio_test.jpg"),
        countdown_s=1,
    )
    service.start({"trace_id": "tr1"})

    assert captured[0].topic == topics.TASK_STARTED
    time.sleep(1.2)

    # shutter fired; task.succeeded emitted
    ts_topics = [e.topic for e in captured]
    assert topics.TASK_SUCCEEDED in ts_topics
    assert "shutter" in sfx.calls
    # HUD countdown cleared
    slots = {d.payload.get("slot") for d in comp.layer(__import__("app.adapters.display", fromlist=["Layer"]).Layer.SYSTEM_HUD).drawables}
    assert SLOT_COUNTDOWN not in slots


def test_cancel_mid_countdown_emits_failure():
    comp = Composition()
    captured = []
    service = PhotoService(
        publish=captured.append, sfx=SpySFX(), composition=comp,
        camera=lambda: Path("/tmp/rio_test.jpg"), countdown_s=1,
    )
    service.start({"trace_id": "tr2"})
    time.sleep(0.1)
    service.cancel()
    time.sleep(1.1)  # ensure no late shutter
    failed = [e for e in captured if e.topic == topics.TASK_FAILED]
    succeeded = [e for e in captured if e.topic == topics.TASK_SUCCEEDED]
    assert len(failed) == 1 and failed[0].payload["error"] == "cancelled"
    assert succeeded == []


def test_interrupt_gate_photo_lock():
    gate = InterruptGate()
    photo = Activity(ActivityKind.EXECUTING, ExecutingKind.PHOTO)
    # New intent during photo is dropped (except system.cancel/ack)
    assert gate.decide(photo, Event(topic=topics.VOICE_INTENT_DETECTED, payload={"intent": "weather.current"})) is Decision.DROP
    # timer.expired is deferred (POL-03)
    assert gate.decide(photo, Event(topic=topics.TIMER_EXPIRED)) is Decision.DEFER
    # cancel passes
    assert gate.decide(photo, Event(topic=topics.VOICE_INTENT_DETECTED, payload={"intent": "system.cancel"})) is Decision.ALLOW


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
