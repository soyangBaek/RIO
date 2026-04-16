"""Context FSM unit tests (scenarios SYS-*)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.events import Event, topics  # noqa: E402
from app.core.state import Context, ExtendedState  # noqa: E402
from app.core.state.context_fsm import ContextThresholds, transition  # noqa: E402


TH = ContextThresholds()


def test_away_to_idle_on_face():
    ext = ExtendedState(face_present=True, last_face_seen_at=10.0,
                        last_user_evidence_at=10.0)
    e = Event(topic=topics.VISION_FACE_DETECTED, timestamp=10.0)
    assert transition(Context.AWAY, e, ext, 10.0) is Context.IDLE


def test_away_to_idle_on_touch():
    ext = ExtendedState(last_user_evidence_at=5.0, last_interaction_at=5.0)
    e = Event(topic=topics.TOUCH_TAP_DETECTED, timestamp=5.0)
    assert transition(Context.AWAY, e, ext, 5.0) is Context.IDLE


def test_sleepy_wakes_only_on_face():
    ext_voice = ExtendedState(face_present=False, last_face_seen_at=195.0)
    e = Event(topic=topics.VOICE_ACTIVITY_STARTED, timestamp=200.0)
    assert transition(Context.SLEEPY, e, ext_voice, 200.0) is Context.SLEEPY

    ext_face = ExtendedState(face_present=True, last_face_seen_at=200.0)
    e2 = Event(topic=topics.VISION_FACE_DETECTED, timestamp=200.0)
    assert transition(Context.SLEEPY, e2, ext_face, 200.0) is Context.IDLE


def test_idle_to_engaged_requires_recent_interaction():
    ext_eng = ExtendedState(face_present=True, last_face_seen_at=50.0,
                            last_interaction_at=50.0)
    e = Event(topic=topics.TOUCH_TAP_DETECTED, timestamp=50.0)
    assert transition(Context.IDLE, e, ext_eng, 50.0) is Context.ENGAGED

    # stale interaction (beyond engagement_window_ms)
    ext_stale = ExtendedState(face_present=True, last_face_seen_at=20.0,
                              last_interaction_at=10.0)
    assert transition(Context.IDLE, e, ext_stale, 20.0) is Context.IDLE


def test_long_idle_to_sleepy():
    ext = ExtendedState(face_present=True, last_interaction_at=0.0,
                        last_user_evidence_at=0.0)
    e = Event(topic=topics.SYSTEM_WORKER_HEARTBEAT, timestamp=121.0)
    assert transition(Context.IDLE, e, ext, 121.0) is Context.SLEEPY
    assert transition(Context.ENGAGED, e, ext, 121.0) is Context.SLEEPY


def test_no_face_long_timeout_to_away():
    ext = ExtendedState(face_present=False, last_face_seen_at=0.0)
    e = Event(topic=topics.SYSTEM_WORKER_HEARTBEAT, timestamp=61.0)
    assert transition(Context.IDLE, e, ext, 61.0) is Context.AWAY
    assert transition(Context.SLEEPY, e, ext, 61.0) is Context.AWAY


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
