"""Oneshot dispatcher unit tests (ONE-01..05)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.events import Event, topics  # noqa: E402
from app.core.state import Context, ExtendedState, Oneshot, OneshotName  # noqa: E402
from app.core.state.oneshot import (  # noqa: E402
    OneshotPolicy,
    dispatch,
    expire_if_done,
    trigger_for_event,
)


POLICY = OneshotPolicy()


def test_welcome_fires_after_long_absence():
    ext = ExtendedState(away_started_at=0.0)
    e = Event(topic=topics.VISION_FACE_DETECTED, timestamp=10.0)
    assert (
        trigger_for_event(e, Context.AWAY, Context.IDLE, ext, 10.0, POLICY)
        is OneshotName.WELCOME
    )


def test_welcome_suppressed_before_min_window():
    ext = ExtendedState(away_started_at=0.0)
    e = Event(topic=topics.VISION_FACE_DETECTED, timestamp=2.0)
    assert trigger_for_event(e, Context.AWAY, Context.IDLE, ext, 2.0, POLICY) is None


def test_startled_on_voice_without_face():
    e = Event(topic=topics.VOICE_ACTIVITY_STARTED, timestamp=1.0)
    ext = ExtendedState(face_present=False)
    assert (
        trigger_for_event(e, Context.IDLE, Context.IDLE, ext, 1.0, POLICY)
        is OneshotName.STARTLED
    )


def test_confused_on_unknown_and_timer_parse_failure():
    assert (
        trigger_for_event(
            Event(topic=topics.VOICE_INTENT_UNKNOWN),
            Context.IDLE, Context.IDLE, ExtendedState(), 0.0, POLICY,
        )
        is OneshotName.CONFUSED
    )
    assert (
        trigger_for_event(
            Event(topic=topics.TASK_FAILED, payload={"kind": "timer_setup"}),
            Context.IDLE, Context.IDLE, ExtendedState(), 0.0, POLICY,
        )
        is OneshotName.CONFUSED
    )


def test_happy_on_stroke_and_success():
    assert (
        trigger_for_event(
            Event(topic=topics.TOUCH_STROKE_DETECTED),
            Context.ENGAGED, Context.ENGAGED, ExtendedState(), 0.0, POLICY,
        )
        is OneshotName.HAPPY
    )
    assert (
        trigger_for_event(
            Event(topic=topics.TASK_SUCCEEDED, payload={"kind": "smarthome"}),
            Context.ENGAGED, Context.ENGAGED, ExtendedState(), 0.0, POLICY,
        )
        is OneshotName.HAPPY
    )


def test_dispatch_priority_preempts():
    active = Oneshot(OneshotName.HAPPY, 20, 1000, 0.0)
    res = dispatch(active, OneshotName.STARTLED, 0.1, POLICY)
    assert res.name is OneshotName.STARTLED


def test_dispatch_same_priority_coalesce_and_replace():
    active = Oneshot(OneshotName.HAPPY, 20, 1000, 0.0)
    # 50% elapsed → coalesce (keep)
    res = dispatch(active, OneshotName.WELCOME, 0.5, POLICY)
    assert res is active
    # 85% elapsed → replace
    res = dispatch(active, OneshotName.WELCOME, 0.85, POLICY)
    assert res.name is OneshotName.WELCOME


def test_expire_if_done():
    o = Oneshot(OneshotName.HAPPY, 20, 1000, 10.0)
    assert expire_if_done(o, 10.5) is o
    assert expire_if_done(o, 11.0) is None
    assert expire_if_done(None, 0.0) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
