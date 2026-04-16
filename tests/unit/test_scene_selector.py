"""T-062: Scene Selector 단위 테스트.

state-machine.md §6 기준 – (Context, Activity, oneshot) → (Mood, UI).
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.state.models import (
    ActivityState, ContextState, ExecutingKind, Mood, OneshotName, UILayout,
)
from src.app.core.state.scene_selector import derive_scene
from src.app.core.state.store import ActiveOneshot


class TestSceneSelector(unittest.TestCase):
    def test_away_idle_dim(self):
        mood, ui = derive_scene(ContextState.AWAY, ActivityState.IDLE, None)
        self.assertEqual(mood, Mood.INACTIVE)
        self.assertEqual(ui, UILayout.NORMAL_FACE_DIM)

    def test_idle_idle_calm(self):
        mood, ui = derive_scene(ContextState.IDLE, ActivityState.IDLE, None)
        self.assertEqual(mood, Mood.CALM)
        self.assertEqual(ui, UILayout.NORMAL_FACE)

    def test_engaged_idle_attentive(self):
        mood, ui = derive_scene(ContextState.ENGAGED, ActivityState.IDLE, None)
        self.assertEqual(mood, Mood.ATTENTIVE)
        self.assertEqual(ui, UILayout.NORMAL_FACE)

    def test_sleepy_idle(self):
        mood, ui = derive_scene(ContextState.SLEEPY, ActivityState.IDLE, None)
        self.assertEqual(mood, Mood.SLEEPY)
        self.assertEqual(ui, UILayout.SLEEP_UI)

    def test_listening_always_attentive(self):
        for ctx in ContextState:
            mood, ui = derive_scene(ctx, ActivityState.LISTENING, None)
            self.assertEqual(mood, Mood.ATTENTIVE)
            self.assertEqual(ui, UILayout.LISTENING_UI)

    def test_executing_photo_camera_ui(self):
        mood, ui = derive_scene(
            ContextState.ENGAGED, ActivityState.EXECUTING, None, ExecutingKind.PHOTO
        )
        self.assertEqual(mood, Mood.ATTENTIVE)
        self.assertEqual(ui, UILayout.CAMERA_UI)

    def test_executing_game_ui(self):
        mood, ui = derive_scene(
            ContextState.ENGAGED, ActivityState.EXECUTING, None, ExecutingKind.GAME
        )
        self.assertEqual(ui, UILayout.GAME_UI)

    def test_alerting_override(self):
        """Alerting → alert mood + AlertUI, Context 무관."""
        for ctx in ContextState:
            mood, ui = derive_scene(ctx, ActivityState.ALERTING, None)
            self.assertEqual(mood, Mood.ALERT)
            self.assertEqual(ui, UILayout.ALERT_UI)

    def test_oneshot_overrides_mood(self):
        """Active oneshot → mood 오버라이드."""
        oneshot = ActiveOneshot(
            name=OneshotName.STARTLED, priority=30,
            started_at=time.time(), duration_ms=600,
        )
        mood, ui = derive_scene(ContextState.IDLE, ActivityState.IDLE, oneshot)
        self.assertEqual(mood, Mood.STARTLED)

    def test_oneshot_during_executing(self):
        """Executing + oneshot → oneshot mood 우선 (§6.1 우선순위 2 > 3)."""
        oneshot = ActiveOneshot(
            name=OneshotName.HAPPY, priority=20,
            started_at=time.time(), duration_ms=1000,
        )
        mood, ui = derive_scene(
            ContextState.ENGAGED, ActivityState.EXECUTING, oneshot, ExecutingKind.SMARTHOME
        )
        self.assertEqual(mood, Mood.HAPPY)  # oneshot overrides attentive

    def test_full_table_no_holes(self):
        """§6.2: 모든 (Activity, Context) 조합에서 UI 반환."""
        kinds = [None, ExecutingKind.PHOTO, ExecutingKind.GAME,
                 ExecutingKind.WEATHER, ExecutingKind.SMARTHOME]
        for activity in ActivityState:
            for context in ContextState:
                for kind in kinds:
                    ek = kind if activity == ActivityState.EXECUTING else None
                    mood, ui = derive_scene(context, activity, None, ek)
                    self.assertIsNotNone(mood)
                    self.assertIsNotNone(ui)


if __name__ == "__main__":
    unittest.main()
