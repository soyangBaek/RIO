from __future__ import annotations

import time
import unittest

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, OneshotName
from src.app.domains.behavior.executor_registry import ExecutionResult
from src.app.main import RioOrchestrator


def success_weather_handler(request):
    return ExecutionResult(
        events=[
            Event.create(topics.TASK_STARTED, "test.weather", payload={"task_id": "weather-ok", "kind": ActionKind.WEATHER.value}),
            Event.create(
                topics.WEATHER_RESULT,
                "test.weather",
                payload={"ok": True, "condition": "rain", "temperature_c": 18.5, "icon_key": "rainy"},
                trace_id=request.trace_id,
            ),
            Event.create(topics.TASK_SUCCEEDED, "test.weather", payload={"task_id": "weather-ok", "kind": ActionKind.WEATHER.value}),
        ]
    )


def failure_weather_handler(request):
    return ExecutionResult(
        events=[
            Event.create(topics.TASK_STARTED, "test.weather", payload={"task_id": "weather-fail", "kind": ActionKind.WEATHER.value}),
            Event.create(topics.WEATHER_RESULT, "test.weather", payload={"ok": False, "message": "network error"}, trace_id=request.trace_id),
            Event.create(topics.TASK_FAILED, "test.weather", payload={"task_id": "weather-fail", "kind": ActionKind.WEATHER.value}),
        ]
    )


class WeatherLookupIntegrationTest(unittest.TestCase):
    def _wait_for_topic(self, orchestrator: RioOrchestrator, topic: str) -> list[Event]:
        processed: list[Event] = []
        deadline = time.time() + 1.0
        while time.time() < deadline:
            batch = orchestrator.drain_bus()
            processed.extend(batch)
            if any(event.topic == topic for event in processed):
                break
            time.sleep(0.01)
        return processed

    def test_weather_success_and_failure(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.WEATHER, success_weather_handler)
        orchestrator.process_event(Event.create(topics.VISION_FACE_DETECTED, "test", payload={"center": (0.5, 0.5)}))
        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "weather.current", "text": "날씨 알려줘"},
            )
        )
        self._wait_for_topic(orchestrator, topics.WEATHER_RESULT)
        self.assertFalse(
            any("Current weather" in text or "Failed to fetch weather" in text for text in orchestrator.tts.history),
            msg="weather result should not emit TTS after SFX migration",
        )
        self.assertIn("weather", orchestrator.sfx.history)
        self.assertIn("Weather OK", [frame.hud.message for frame in orchestrator.renderer.history])

        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.WEATHER, failure_weather_handler)
        orchestrator.process_event(Event.create(topics.VISION_FACE_DETECTED, "test", payload={"center": (0.5, 0.5)}))
        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "weather.current", "text": "날씨 알려줘"},
            )
        )
        self._wait_for_topic(orchestrator, topics.WEATHER_RESULT)
        self.assertEqual(orchestrator.store.snapshot().active_oneshot.name, OneshotName.CONFUSED)
        self.assertIn("weather_failed", orchestrator.sfx.history)
        self.assertIn("Weather failed", [frame.hud.message for frame in orchestrator.renderer.history])


if __name__ == "__main__":
    unittest.main()
