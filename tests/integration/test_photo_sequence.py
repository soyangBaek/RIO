from __future__ import annotations

import unittest

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ActivityState
from src.app.domains.behavior.executor_registry import ExecutionResult
from src.app.main import RioOrchestrator


class SlowPhotoHandler:
    def __call__(self, request):
        return ExecutionResult(
            events=[
                Event.create(topics.TASK_STARTED, "test.photo", payload={"task_id": "photo-1", "kind": ActionKind.PHOTO.value})
            ]
        )


class PhotoSequenceIntegrationTest(unittest.TestCase):
    def test_photo_lock_ignores_new_intents_and_delays_alert(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.PHOTO, SlowPhotoHandler())

        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "camera.capture", "text": "사진 찍어줘"},
            )
        )
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)
        self.assertEqual(orchestrator.store.snapshot().extended.active_executing_kind, ActionKind.PHOTO)

        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "weather.current", "text": "날씨 알려줘"},
            )
        )
        self.assertIsNone(orchestrator.store.snapshot().extended.deferred_intent)

        orchestrator.process_event(Event.create(topics.TIMER_EXPIRED, "test", payload={"label": "photo"}))
        self.assertEqual(len(orchestrator.held_alerts), 1)
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)

        orchestrator.process_event(
            Event.create(
                topics.TASK_SUCCEEDED,
                "test.photo",
                payload={"task_id": "photo-1", "kind": ActionKind.PHOTO.value},
            )
        )
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.ALERTING)
        self.assertEqual(len(orchestrator.held_alerts), 0)
        self.assertIn("shutter", orchestrator.sfx.history)
        self.assertTrue(any("Photo" in text for text in orchestrator.tts.history))


if __name__ == "__main__":
    unittest.main()
