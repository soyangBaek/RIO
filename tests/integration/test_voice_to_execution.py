from __future__ import annotations

import unittest

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ActivityState
from src.app.domains.behavior.executor_registry import ExecutionResult
from src.app.main import RioOrchestrator


def fake_weather_handler(request):
    return ExecutionResult(
        events=[
            Event.create(topics.TASK_STARTED, "test.weather", payload={"task_id": "weather-1", "kind": ActionKind.WEATHER.value}),
            Event.create(
                topics.WEATHER_RESULT,
                "test.weather",
                payload={"ok": True, "condition": "맑음", "temperature_c": 22.0},
                trace_id=request.trace_id,
            ),
            Event.create(topics.TASK_SUCCEEDED, "test.weather", payload={"task_id": "weather-1", "kind": ActionKind.WEATHER.value}),
        ]
    )


class VoiceToExecutionIntegrationTest(unittest.TestCase):
    def test_voice_flow_runs_to_completion(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.WEATHER, fake_weather_handler)
        orchestrator.publish(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        orchestrator.publish(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "weather.current", "text": "날씨 알려줘"},
            )
        )
        processed = orchestrator.drain_bus()
        seen_topics = {event.topic for event in processed}

        self.assertIn(topics.WEATHER_RESULT, seen_topics)
        self.assertIn(topics.TASK_SUCCEEDED, seen_topics)
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.IDLE)
        self.assertTrue(any("맑음" in text for text in orchestrator.tts.history))


if __name__ == "__main__":
    unittest.main()
