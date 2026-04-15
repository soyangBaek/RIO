from __future__ import annotations

import unittest

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind
from src.app.domains.smart_home.service import SmartHomeService
from src.app.main import RioOrchestrator


class FakeHomeClient:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def control(self, content: str):
        if self.ok:
            return {"ok": True, "message": f"{content} success"}
        return {"ok": False, "message": f"{content} failed"}


class SmartHomeFlowIntegrationTest(unittest.TestCase):
    def test_success_and_failure_paths(self) -> None:
        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.SMARTHOME, SmartHomeService(FakeHomeClient(ok=True)))
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
        self.assertTrue(any("success" in text for text in orchestrator.tts.history))

        orchestrator = RioOrchestrator()
        orchestrator.registry.register(ActionKind.SMARTHOME, SmartHomeService(FakeHomeClient(ok=False)))
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
        self.assertTrue(any("failed" in text for text in orchestrator.tts.history))


if __name__ == "__main__":
    unittest.main()
