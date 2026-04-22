from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.activity_fsm import transition_activity
from src.app.core.state.models import ActionKind, ActivityState, RuntimeState
from src.app.domains.behavior.interrupts import InterruptAction, evaluate_interrupt


class ActivityFSMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_idle_to_listening(self) -> None:
        event = Event.create(topics.VOICE_ACTIVITY_STARTED, "test", timestamp=self.now)
        state, kind = transition_activity(ActivityState.IDLE, event)
        self.assertEqual((state, kind), (ActivityState.LISTENING, None))

    def test_listening_to_executing_weather(self) -> None:
        event = Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "weather.current"},
            timestamp=self.now,
        )
        state, kind = transition_activity(ActivityState.LISTENING, event)
        self.assertEqual((state, kind), (ActivityState.EXECUTING, ActionKind.WEATHER))

    def test_timer_expired_preempts_to_alerting(self) -> None:
        event = Event.create(topics.TIMER_EXPIRED, "test", timestamp=self.now)
        state, kind = transition_activity(ActivityState.EXECUTING, event, ActionKind.SMARTHOME)
        self.assertEqual((state, kind), (ActivityState.ALERTING, None))

    def test_alerting_to_idle_on_ack(self) -> None:
        event = Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "system.ack"},
            timestamp=self.now,
        )
        state, kind = transition_activity(ActivityState.ALERTING, event)
        self.assertEqual((state, kind), (ActivityState.IDLE, None))

    def test_interrupt_policy_photo_locks_new_intent(self) -> None:
        runtime = RuntimeState(activity_state=ActivityState.EXECUTING)
        runtime.extended.active_executing_kind = ActionKind.PHOTO
        event = Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "weather.current"},
            timestamp=self.now,
        )
        decision = evaluate_interrupt(runtime, event)
        self.assertEqual(decision.action, InterruptAction.DROP)

    def test_interrupt_policy_photo_allows_cancel_only(self) -> None:
        runtime = RuntimeState(activity_state=ActivityState.EXECUTING)
        runtime.extended.active_executing_kind = ActionKind.PHOTO
        cancel = Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "system.cancel"},
            timestamp=self.now,
        )
        self.assertEqual(evaluate_interrupt(runtime, cancel).action, InterruptAction.ALLOW)

        # "확인" 포함 나머지 모든 음성 의도는 차단
        ack = Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "system.ack"},
            timestamp=self.now,
        )
        self.assertEqual(evaluate_interrupt(runtime, ack).action, InterruptAction.DROP)

    def test_interrupt_policy_photo_drops_gesture_and_touch(self) -> None:
        runtime = RuntimeState(activity_state=ActivityState.EXECUTING)
        runtime.extended.active_executing_kind = ActionKind.PHOTO
        for topic, payload in (
            (topics.VISION_GESTURE_DETECTED, {"gesture": "fist"}),
            (topics.TOUCH_TAP_DETECTED, {}),
            (topics.TOUCH_STROKE_DETECTED, {}),
            (topics.VOICE_INTENT_UNKNOWN, {}),
        ):
            event = Event.create(topic, "test", payload=payload, timestamp=self.now)
            self.assertEqual(
                evaluate_interrupt(runtime, event).action,
                InterruptAction.DROP,
                f"{topic} should be dropped during photo",
            )

    def test_interrupt_policy_photo_allows_task_completion(self) -> None:
        # 촬영 자체를 끝내는 TASK_SUCCEEDED 는 당연히 통과해야 한다.
        runtime = RuntimeState(activity_state=ActivityState.EXECUTING)
        runtime.extended.active_executing_kind = ActionKind.PHOTO
        for topic in (topics.TASK_SUCCEEDED, topics.TASK_FAILED):
            event = Event.create(topic, "test", payload={"kind": "photo"}, timestamp=self.now)
            self.assertEqual(evaluate_interrupt(runtime, event).action, InterruptAction.ALLOW)

    def test_interrupt_policy_short_actions_defer_latest_intent(self) -> None:
        runtime = RuntimeState(activity_state=ActivityState.EXECUTING)
        runtime.extended.active_executing_kind = ActionKind.SMARTHOME
        event = Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "weather.current"},
            timestamp=self.now,
        )
        decision = evaluate_interrupt(runtime, event)
        self.assertEqual(decision.action, InterruptAction.DEFER_INTENT)
        self.assertEqual(decision.deferred_payload["intent"], "weather.current")


if __name__ == "__main__":
    unittest.main()
