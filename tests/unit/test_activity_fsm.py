"""Activity FSM unit tests (VOICE-*, POL-*)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.events import Event, topics  # noqa: E402
from app.core.state import Activity, ActivityKind, ExecutingKind, ExtendedState  # noqa: E402
from app.core.state.activity_fsm import (  # noqa: E402
    ActivityThresholds,
    intent_to_executing_kind,
    transition,
)

IDLE = Activity(ActivityKind.IDLE)
LIS = Activity(ActivityKind.LISTENING)
ALR = Activity(ActivityKind.ALERTING)
PHOTO = Activity(ActivityKind.EXECUTING, ExecutingKind.PHOTO)


def test_idle_to_listening_on_voice_started():
    ext = ExtendedState(activity_started_at=0.0)
    e = Event(topic=topics.VOICE_ACTIVITY_STARTED, timestamp=1.0)
    assert transition(IDLE, e, ext, 1.0) == LIS


def test_intent_routes_to_executing_kind():
    ext = ExtendedState(activity_started_at=1.0)
    for intent, expected in [
        ("camera.capture", ExecutingKind.PHOTO),
        ("timer.create", ExecutingKind.TIMER_SETUP),
        ("smarthome.aircon.on", ExecutingKind.SMARTHOME),
        ("weather.current", ExecutingKind.WEATHER),
        ("dance.start", ExecutingKind.DANCE),
        ("ui.game_mode.enter", ExecutingKind.GAME),
    ]:
        e = Event(topic=topics.VOICE_INTENT_DETECTED, payload={"intent": intent}, timestamp=2.0)
        a = transition(LIS, e, ext, 2.0)
        assert a.kind is ActivityKind.EXECUTING and a.executing is expected, intent


def test_system_cancel_exits_to_idle():
    ext = ExtendedState(activity_started_at=0.0)
    cancel = Event(topic=topics.VOICE_INTENT_DETECTED, payload={"intent": "system.cancel"})
    for cur in (LIS, PHOTO, ALR):
        assert transition(cur, cancel, ext, 0.0) == IDLE


def test_system_ack_only_in_alerting():
    ext = ExtendedState(activity_started_at=0.0)
    ack = Event(topic=topics.VOICE_INTENT_DETECTED, payload={"intent": "system.ack"})
    assert transition(ALR, ack, ext, 0.0) == IDLE
    assert transition(LIS, ack, ext, 0.0) == LIS  # ignored outside Alerting


def test_timer_expired_preempts_to_alerting():
    ext = ExtendedState(activity_started_at=0.0)
    e = Event(topic=topics.TIMER_EXPIRED, timestamp=3.0)
    for cur in (IDLE, LIS, PHOTO):
        assert transition(cur, e, ext, 3.0) == ALR


def test_task_done_returns_to_idle():
    ext = ExtendedState(activity_started_at=2.0)
    e = Event(topic=topics.TASK_SUCCEEDED, timestamp=3.0, payload={"kind": "photo"})
    assert transition(PHOTO, e, ext, 3.0) == IDLE
    e2 = Event(topic=topics.TASK_FAILED, timestamp=3.0)
    assert transition(PHOTO, e2, ext, 3.0) == IDLE


def test_listening_timeout_returns_to_idle():
    th = ActivityThresholds()
    ext = ExtendedState(activity_started_at=0.0)
    e = Event(topic=topics.SYSTEM_WORKER_HEARTBEAT, timestamp=6.0)
    assert transition(LIS, e, ext, 6.0, th) == IDLE
    assert transition(LIS, e, ext, 4.0, th) == LIS


def test_intent_mapper_rejects_unknown():
    assert intent_to_executing_kind("bogus.intent") is None
    assert intent_to_executing_kind("system.cancel") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
