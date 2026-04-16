"""Scene Selector unit tests — Mood/UI matrix (state-machine §6)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.state import (  # noqa: E402
    Activity, ActivityKind, Context, ExecutingKind, Mood, Oneshot,
    OneshotName, UI,
)
from app.core.state.scene_selector import derive  # noqa: E402


IDLE = Activity(ActivityKind.IDLE)
LIS = Activity(ActivityKind.LISTENING)
ALR = Activity(ActivityKind.ALERTING)
PHOTO = Activity(ActivityKind.EXECUTING, ExecutingKind.PHOTO)
GAME = Activity(ActivityKind.EXECUTING, ExecutingKind.GAME)
WEATHER = Activity(ActivityKind.EXECUTING, ExecutingKind.WEATHER)


def test_idle_matrix():
    assert derive(Context.AWAY, IDLE).mood is Mood.INACTIVE
    assert derive(Context.AWAY, IDLE).ui is UI.NORMAL_FACE
    assert derive(Context.IDLE, IDLE).mood is Mood.CALM
    assert derive(Context.ENGAGED, IDLE).mood is Mood.ATTENTIVE
    assert derive(Context.SLEEPY, IDLE).mood is Mood.SLEEPY
    assert derive(Context.SLEEPY, IDLE).ui is UI.SLEEP_UI


def test_listening_lock():
    for ctx in (Context.AWAY, Context.IDLE, Context.ENGAGED, Context.SLEEPY):
        s = derive(ctx, LIS)
        assert s.mood is Mood.ATTENTIVE and s.ui is UI.LISTENING_UI


def test_executing_ui_table():
    assert derive(Context.IDLE, PHOTO).ui is UI.CAMERA_UI
    assert derive(Context.IDLE, GAME).ui is UI.GAME_UI
    assert derive(Context.IDLE, WEATHER).ui is UI.NORMAL_FACE


def test_alerting_override_everything():
    o = Oneshot(OneshotName.HAPPY, 20, 1000, 0.0)
    s = derive(Context.SLEEPY, ALR, o)
    assert s.mood is Mood.ALERT and s.ui is UI.ALERT_UI


def test_oneshot_overlays_focus_lock():
    # Executing focus lock → attentive, but oneshot should overlay.
    s = derive(Context.IDLE, PHOTO, Oneshot(OneshotName.HAPPY, 20, 1000, 0.0))
    assert s.mood is Mood.HAPPY  # ONE overlay wins over focus lock


def test_welcome_overlay_preserves_ui():
    s = derive(Context.SLEEPY, IDLE, Oneshot(OneshotName.WELCOME, 20, 1500, 0.0))
    assert s.mood is Mood.HAPPY  # welcome mood == happy
    assert s.ui is UI.SLEEP_UI  # UI still follows context table


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
