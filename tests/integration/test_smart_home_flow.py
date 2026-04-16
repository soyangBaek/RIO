from __future__ import annotations

import unittest

from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.terminal_input import TerminalVoiceInput
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ContextState
from src.app.domains.smart_home.service import SmartHomeService
from src.app.main import RioOrchestrator


class FakeHomeClient:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.calls: list[str] = []

    def control(self, content: str):
        self.calls.append(content)
        if self.ok:
            return {"ok": True, "message": f"{content} success"}
        return {"ok": False, "message": f"{content} failed"}


class SmartHomeFlowIntegrationTest(unittest.TestCase):
    def test_success_and_failure_paths(self) -> None:
        orchestrator = RioOrchestrator()
        success_client = FakeHomeClient(ok=True)
        orchestrator.registry.register(ActionKind.SMARTHOME, SmartHomeService(success_client))
        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        processed = orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "smarthome.aircon.on", "text": "에어컨 켜줘"},
            )
        )
        seen_topics = {event.topic for event in processed}
        self.assertIn(topics.SMARTHOME_RESULT, seen_topics)
        self.assertEqual(success_client.calls, ["aircon.living_room:on"])
        self.assertTrue(any("success" in text for text in orchestrator.tts.history))

        orchestrator = RioOrchestrator()
        failure_client = FakeHomeClient(ok=False)
        orchestrator.registry.register(ActionKind.SMARTHOME, SmartHomeService(failure_client))
        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
        processed = orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "smarthome.aircon.on", "text": "에어컨 켜줘"},
            )
        )
        failed_results = [event for event in processed if event.topic == topics.SMARTHOME_RESULT]
        self.assertTrue(failed_results)
        self.assertFalse(failed_results[-1].payload["ok"])
        self.assertEqual(failure_client.calls, ["aircon.living_room:on"])
        self.assertTrue(any("failed" in text for text in orchestrator.tts.history))

    def test_dynamic_temperature_command_builds_http_payload(self) -> None:
        orchestrator = RioOrchestrator()
        client = FakeHomeClient(ok=True)
        orchestrator.registry.register(ActionKind.SMARTHOME, SmartHomeService(client))
        orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))

        processed = orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={
                    "intent": "smarthome.aircon.set_temperature",
                    "text": "온도 28도로 맞춰줘",
                    "temperature_c": 28,
                    "device_key": "aircon",
                    "action": "set_temperature",
                },
            )
        )

        request_events = [event for event in processed if event.topic == topics.SMARTHOME_REQUEST_SENT]
        self.assertTrue(request_events)
        self.assertEqual(client.calls, ["aircon.living_room:set_temperature:28"])
        self.assertEqual(request_events[-1].payload["content"], "aircon.living_room:set_temperature:28")
        self.assertEqual(request_events[-1].payload["params"]["temperature_c"], 28)
        self.assertTrue(any("success" in text for text in orchestrator.tts.history))

    def test_smarthome_command_executes_even_without_visible_face(self) -> None:
        orchestrator = RioOrchestrator()
        client = FakeHomeClient(ok=True)
        orchestrator.registry.register(ActionKind.SMARTHOME, SmartHomeService(client))
        terminal = TerminalVoiceInput(IntentNormalizer())

        self.assertEqual(orchestrator.store.snapshot().context_state, ContextState.AWAY)
        self.assertFalse(orchestrator.store.snapshot().extended.face_present)

        processed: list[Event] = []
        for event in terminal.build_events("에어컨 켜줘"):
            processed.extend(orchestrator.process_event(event))

        self.assertEqual(client.calls, ["aircon.living_room:on"])
        self.assertTrue(any(event.topic == topics.SMARTHOME_REQUEST_SENT for event in processed))
        self.assertTrue(any(event.topic == topics.SMARTHOME_RESULT for event in processed))
        self.assertEqual(orchestrator.store.snapshot().context_state, ContextState.IDLE)
        self.assertTrue(any("success" in text for text in orchestrator.tts.history))


if __name__ == "__main__":
    unittest.main()
