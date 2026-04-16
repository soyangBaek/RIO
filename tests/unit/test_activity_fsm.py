"""T-060: Activity FSM 단위 테스트.

state-machine.md §4 기준.
"""
import sys
import unittest

sys.path.insert(0, ".")

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.activity_fsm import activity_transition
from src.app.core.state.models import ActivityState, ExecutingKind
from src.app.core.state.store import Store

DEFAULT_CONFIG = {}


class TestActivityFSM(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.config = DEFAULT_CONFIG

    def test_idle_to_listening_on_voice_started(self):
        event = Event(topic=Topics.VOICE_ACTIVITY_STARTED, source="audio_worker")
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], ActivityState.IDLE)
        self.assertEqual(result[1], ActivityState.LISTENING)

    def test_listening_to_executing_on_intent(self):
        self.store.activity_state = ActivityState.LISTENING
        event = Event(
            topic=Topics.VOICE_INTENT_DETECTED,
            source="audio_worker",
            payload={"intent": "camera.capture", "text": "사진 찍어"},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], ActivityState.EXECUTING)
        self.assertEqual(result[2], ExecutingKind.PHOTO)

    def test_listening_to_idle_on_unknown(self):
        self.store.activity_state = ActivityState.LISTENING
        event = Event(
            topic=Topics.VOICE_INTENT_UNKNOWN,
            source="audio_worker",
            payload={"text": "blah", "confidence": 0.3},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], ActivityState.IDLE)

    def test_executing_to_idle_on_success(self):
        self.store.activity_state = ActivityState.EXECUTING
        self.store.active_executing_kind = ExecutingKind.WEATHER
        event = Event(
            topic=Topics.TASK_SUCCEEDED,
            source="main/executor",
            payload={"task_id": "abc", "kind": "weather"},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], ActivityState.IDLE)

    def test_idle_to_alerting_on_timer_expired(self):
        event = Event(
            topic=Topics.TIMER_EXPIRED,
            source="main/scheduler",
            payload={"timer_id": "t1", "label": "test"},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], ActivityState.ALERTING)

    def test_alerting_to_idle_on_tap(self):
        self.store.activity_state = ActivityState.ALERTING
        event = Event(
            topic=Topics.TOUCH_TAP_DETECTED,
            source="main/touch",
            payload={"x": 0.5, "y": 0.5},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], ActivityState.IDLE)

    def test_executing_photo_blocks_timer_alerting(self):
        """Executing(photo) 중 timer.expired → Alerting 전이 차단."""
        self.store.activity_state = ActivityState.EXECUTING
        self.store.active_executing_kind = ExecutingKind.PHOTO
        event = Event(
            topic=Topics.TIMER_EXPIRED,
            source="main/scheduler",
            payload={"timer_id": "t1"},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNone(result)  # photo blocks it

    def test_smarthome_intent_mapping(self):
        self.store.activity_state = ActivityState.LISTENING
        event = Event(
            topic=Topics.VOICE_INTENT_DETECTED,
            source="audio_worker",
            payload={"intent": "smarthome.aircon.on"},
        )
        result = activity_transition(self.store, event, self.config)
        self.assertIsNotNone(result)
        self.assertEqual(result[2], ExecutingKind.SMARTHOME)


if __name__ == "__main__":
    unittest.main()
