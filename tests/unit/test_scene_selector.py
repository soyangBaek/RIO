from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.app.core.state.models import (
    ActionKind,
    ActivityState,
    ContextState,
    ExtendedState,
    Mood,
    Oneshot,
    OneshotName,
    UIState,
)
from src.app.core.state.scene_selector import select_scene


class SceneSelectorTest(unittest.TestCase):
    def test_idle_context_matrix(self) -> None:
        expected = {
            ContextState.AWAY: (UIState.NORMAL_FACE, Mood.INACTIVE, True),
            ContextState.IDLE: (UIState.NORMAL_FACE, Mood.CALM, False),
            ContextState.ENGAGED: (UIState.NORMAL_FACE, Mood.ATTENTIVE, False),
            ContextState.SLEEPY: (UIState.SLEEP_UI, Mood.SLEEPY, False),
        }
        for context, (ui, mood, dimmed) in expected.items():
            with self.subTest(context=context):
                scene = select_scene(context, ActivityState.IDLE, ExtendedState(), None)
                self.assertEqual(scene.ui, ui)
                self.assertEqual(scene.mood, mood)
                self.assertEqual(scene.dimmed, dimmed)

    def test_listening_uses_search_indicator_without_face(self) -> None:
        scene = select_scene(ContextState.IDLE, ActivityState.LISTENING, ExtendedState(face_present=False), None)
        self.assertEqual(scene.ui, UIState.LISTENING_UI)
        self.assertTrue(scene.search_indicator)
        self.assertEqual(scene.mood, Mood.ATTENTIVE)

    def test_alerting_override(self) -> None:
        scene = select_scene(ContextState.AWAY, ActivityState.ALERTING, ExtendedState(), None)
        self.assertEqual(scene.ui, UIState.ALERT_UI)
        self.assertEqual(scene.mood, Mood.ALERT)

    def test_executing_kind_routes_ui(self) -> None:
        extended = ExtendedState(active_executing_kind=ActionKind.PHOTO)
        scene = select_scene(ContextState.ENGAGED, ActivityState.EXECUTING, extended, None)
        self.assertEqual(scene.ui, UIState.CAMERA_UI)
        self.assertEqual(scene.mood, Mood.ATTENTIVE)

        extended = ExtendedState(active_executing_kind=ActionKind.GAME)
        scene = select_scene(ContextState.IDLE, ActivityState.EXECUTING, extended, None)
        self.assertEqual(scene.ui, UIState.GAME_UI)

    def test_oneshot_overrides_mood(self) -> None:
        oneshot = Oneshot(
            name=OneshotName.WELCOME,
            priority=20,
            duration_ms=1000,
            started_at=datetime.now(timezone.utc),
        )
        scene = select_scene(ContextState.IDLE, ActivityState.IDLE, ExtendedState(), oneshot)
        self.assertEqual(scene.mood, Mood.WELCOME)

    def test_game_ui_mode_persists_game_ui_and_attentive_mood(self) -> None:
        scene = select_scene(
            ContextState.IDLE,
            ActivityState.IDLE,
            ExtendedState(ui_mode="game"),
            None,
        )
        self.assertEqual(scene.ui, UIState.GAME_UI)
        self.assertEqual(scene.mood, Mood.ATTENTIVE)


if __name__ == "__main__":
    unittest.main()
