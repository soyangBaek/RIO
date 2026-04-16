"""Long scenario replay — chains face/voice injections through the full
reducer pipeline to exercise SYS-07 / SYS-09 style timing.

Runs in simulated time (not real sleep) so the whole script completes in
milliseconds regardless of scenario length.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.bus import Router  # noqa: E402
from app.core.events import Event, topics  # noqa: E402
from app.core.state import Context, StateStore  # noqa: E402
from app.core.state.reducers import Reducer  # noqa: E402

from face_event_replay import face_detected, face_lost  # noqa: E402


def run_sys07_to_away_and_welcome_back() -> dict:
    """Exercise the full SYS-07 → SYS-09 arc.

    1. Face appears → Idle.
    2. No interaction for 120 s → Sleepy (SYS-07).
    3. Face disappears for 60 s while Sleepy → Away.
    4. Face returns after a long absence → Idle + welcome oneshot (SYS-09).
    """
    store = StateStore()
    router = Router()
    reducer = Reducer(store, router)

    reducer.reduce(face_detected(ts=0.0, center=(0.5, 0.5)))
    assert store.get().context is Context.IDLE

    # 130 s tick with no further interaction → Sleepy
    reducer.reduce(
        Event(topic=topics.SYSTEM_WORKER_HEARTBEAT, timestamp=130.0, source="sim")
    )
    assert store.get().context is Context.SLEEPY

    # Face lost while Sleepy.
    reducer.reduce(face_lost(ts=131.0, last_seen_at=131.0))
    # 60+ seconds later → Away
    reducer.reduce(
        Event(topic=topics.SYSTEM_WORKER_HEARTBEAT, timestamp=200.0, source="sim")
    )
    assert store.get().context is Context.AWAY

    # Face returns after long absence → Idle + welcome
    reducer.reduce(face_detected(ts=400.0, center=(0.5, 0.5)))
    state = store.get()
    assert state.context is Context.IDLE
    assert state.active_oneshot is not None
    assert state.active_oneshot.name.value == "welcome"

    return {
        "final_context": state.context.value,
        "oneshot": state.active_oneshot.name.value,
    }


def test_long_scenario():
    result = run_sys07_to_away_and_welcome_back()
    assert result == {"final_context": "idle", "oneshot": "welcome"}


if __name__ == "__main__":
    test_long_scenario()
    print("ok: long_scenario_playback self-test")
