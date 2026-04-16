"""T-059: Context FSM 단위 테스트.

state-machine.md §3 기준.
Away/Idle/Engaged/Sleepy 전이 검증.
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.context_fsm import context_transition
from src.app.core.state.models import ContextState
from src.app.core.state.store import Store

DEFAULT_CONFIG = {
    "presence": {
        "face_lost_timeout_ms": 800,
        "away_timeout_ms": 60000,
        "welcome_min_away_ms": 3000,
    },
    "behavior": {
        "idle_to_sleepy_timeout_ms": 120000,
    },
}


class TestContextFSM(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.config = DEFAULT_CONFIG

    def test_initial_state_is_away(self):
        self.assertEqual(self.store.context_state, ContextState.AWAY)

    def test_away_to_idle_on_face_detected(self):
        event = Event(
            topic=Topics.VISION_FACE_DETECTED,
            source="vision_worker",
            payload={"bbox": [0.3, 0.3, 0.1, 0.1], "center": [0.35, 0.35], "confidence": 0.9},
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result, (ContextState.AWAY, ContextState.IDLE))

    def test_away_to_idle_on_voice(self):
        event = Event(
            topic=Topics.VOICE_ACTIVITY_STARTED,
            source="audio_worker",
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result, (ContextState.AWAY, ContextState.IDLE))

    def test_away_to_idle_on_touch(self):
        event = Event(
            topic=Topics.TOUCH_TAP_DETECTED,
            source="main/touch",
            payload={"x": 0.5, "y": 0.5},
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result, (ContextState.AWAY, ContextState.IDLE))

    def test_idle_to_engaged_on_interaction_with_face(self):
        self.store.context_state = ContextState.IDLE
        self.store.face_present = True
        event = Event(
            topic=Topics.VOICE_INTENT_DETECTED,
            source="audio_worker",
            payload={"intent": "weather.current", "text": "날씨"},
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result, (ContextState.IDLE, ContextState.ENGAGED))

    def test_idle_stays_without_face(self):
        self.store.context_state = ContextState.IDLE
        self.store.face_present = False
        event = Event(
            topic=Topics.VOICE_INTENT_DETECTED,
            source="audio_worker",
            payload={"intent": "weather.current"},
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNone(result)  # no face → no engaged

    def test_sleepy_to_idle_on_face_only(self):
        self.store.context_state = ContextState.SLEEPY
        event = Event(
            topic=Topics.VISION_FACE_DETECTED,
            source="vision_worker",
            payload={"bbox": [0.3, 0.3, 0.1, 0.1], "center": [0.35, 0.35], "confidence": 0.9},
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result, (ContextState.SLEEPY, ContextState.IDLE))

    def test_sleepy_no_wake_on_voice(self):
        """Sleepy → Idle: 음성만으로는 깨지 않음."""
        self.store.context_state = ContextState.SLEEPY
        event = Event(
            topic=Topics.VOICE_ACTIVITY_STARTED,
            source="audio_worker",
        )
        result = context_transition(self.store, event, self.config)
        self.assertIsNone(result)  # voice alone doesn't wake from Sleepy


if __name__ == "__main__":
    unittest.main()
