from __future__ import annotations

import unittest

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, OneshotName
from src.app.domains.behavior.executor_registry import ExecutionResult
from src.app.main import RioOrchestrator


class InstantPhotoHandler:
    def __call__(self, request):
        return ExecutionResult(
            events=[
                Event.create(topics.TASK_STARTED, "test.photo", payload={"task_id": "photo-1", "kind": ActionKind.PHOTO.value}),
                Event.create(
                    topics.TASK_SUCCEEDED,
                    "test.photo",
                    payload={"task_id": "photo-1", "kind": ActionKind.PHOTO.value, "photo_path": "data/photos/test.jpg"},
                    trace_id=request.trace_id,
                ),
            ]
        )


class InputReactionIntegrationTest(unittest.TestCase):
    def test_wave_gesture_triggers_greeting_feedback(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.process_event(Event.create(topics.VISION_FACE_DETECTED, "test", payload={"center": (0.5, 0.5)}))
        orchestrator.process_event(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "test",
                payload={"gesture": "wave", "confidence": 1.0},
            )
        )

        self.assertEqual(orchestrator.store.snapshot().active_oneshot.name, OneshotName.WELCOME)
        self.assertIn("안녕!", orchestrator.tts.history)
        self.assertIn("안녕!", [frame.hud.message for frame in orchestrator.renderer.history])

    def test_finger_gun_triggers_startled_feedback(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.process_event(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "test",
                payload={"gesture": "finger_gun", "confidence": 1.0},
            )
        )

        self.assertEqual(orchestrator.store.snapshot().active_oneshot.name, OneshotName.STARTLED)
        self.assertIn("빵야!", orchestrator.tts.history)
        self.assertIn("빵야!", [frame.hud.message for frame in orchestrator.renderer.history])

    def test_v_sign_triggers_photo_capture_flow(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.PHOTO, InstantPhotoHandler())
        orchestrator.process_event(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "test",
                payload={"gesture": "v_sign", "confidence": 1.0},
            )
        )

        self.assertTrue(any("사진" in text for text in orchestrator.tts.history))
        self.assertIn("사진 저장 완료", [frame.hud.message for frame in orchestrator.renderer.history])

    def test_touch_stroke_triggers_happy_reaction(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.process_event(Event.create(topics.TOUCH_STROKE_DETECTED, "test", payload={"path": [(0, 0), (30, 0)]}))

        self.assertEqual(orchestrator.store.snapshot().active_oneshot.name, OneshotName.HAPPY)
        self.assertIn("좋아!", [frame.hud.message for frame in orchestrator.renderer.history])
        self.assertIn("happy", orchestrator.sfx.history)

    def test_game_mode_persists_and_head_direction_feedback_is_visible(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.process_event(Event.create(topics.VISION_FACE_DETECTED, "test", payload={"center": (0.5, 0.5)}))
        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "ui.game_mode.enter", "text": "게임 모드로 바꿔줘"},
            )
        )

        self.assertEqual(orchestrator.store.snapshot().extended.ui_mode, "game")
        self.assertEqual(orchestrator.renderer.history[-1].ui, "GameUI")

        orchestrator.process_event(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "test",
                payload={"gesture": "head_left", "confidence": 1.0},
            )
        )

        self.assertIn("참참참: 왼쪽", [frame.hud.message for frame in orchestrator.renderer.history])
        self.assertIn("game_move", orchestrator.sfx.history)


if __name__ == "__main__":
    unittest.main()
