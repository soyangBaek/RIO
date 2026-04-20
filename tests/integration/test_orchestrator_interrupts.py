"""로드맵 §1 회귀 고정: dance/photo 진행 중 인터럽트 정책.

핵심 불변:
- dance EXECUTING 동안 임의의 voice intent(gesture mapper 경유 포함)는 drop.
- dance 동안 system.cancel 만 허용되고, 타이머는 해제된다.
- photo EXECUTING 동안 voice intent 는 drop, timer alert 는 held 되었다가 완료 시 재생.
"""
from __future__ import annotations

import unittest

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ActivityState
from src.app.domains.behavior.executor_registry import ExecutionResult
from src.app.main import RioOrchestrator


class FakeLongRunningHandler:
    """TASK_STARTED 만 바로 반환하고 실제 threading.Timer 는 돌리지 않는 핸들러."""

    def __init__(self, kind: ActionKind, task_id: str) -> None:
        self.kind = kind
        self.task_id = task_id
        self.call_count = 0

    def __call__(self, request) -> ExecutionResult:
        self.call_count += 1
        return ExecutionResult(
            events=[
                Event.create(
                    topics.TASK_STARTED,
                    "test.fake",
                    payload={"task_id": self.task_id, "kind": self.kind.value},
                )
            ]
        )


def _drive_to_dance_executing(orchestrator: RioOrchestrator) -> None:
    orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
    orchestrator.process_event(
        Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "dance.start", "text": "댄스모드"},
        )
    )


def _drive_to_photo_executing(orchestrator: RioOrchestrator) -> None:
    orchestrator.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "test"))
    orchestrator.process_event(
        Event.create(
            topics.VOICE_INTENT_DETECTED,
            "test",
            payload={"intent": "camera.capture", "text": "사진 찍어줘"},
        )
    )


class OrchestratorInterruptRegressionTest(unittest.TestCase):
    def test_dance_drops_voice_intents_including_synthetic_wave(self) -> None:
        orchestrator = RioOrchestrator()
        fake_dance = FakeLongRunningHandler(ActionKind.DANCE, "dance-1")
        orchestrator.registry.register(ActionKind.DANCE, fake_dance)

        _drive_to_dance_executing(orchestrator)
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)
        self.assertEqual(
            orchestrator.store.snapshot().extended.active_executing_kind,
            ActionKind.DANCE,
        )

        # 사용자가 요구한 시나리오: dance 중 wave 가 감지돼도 반응 없어야 함.
        # gesture_mapper 가 아직 wave 를 매핑하지 않지만, 미래에 매핑돼도 DROP 돼야 하므로
        # synthetic intent 로 회귀 고정한다.
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "greet", "text": "(synthetic wave)"},
            )
        )
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "camera.capture", "text": "사진"},
            )
        )
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "weather.current", "text": "날씨"},
            )
        )

        snapshot = orchestrator.store.snapshot()
        self.assertEqual(snapshot.activity_state, ActivityState.EXECUTING)
        self.assertEqual(snapshot.extended.active_executing_kind, ActionKind.DANCE)
        # long-action 은 DEFER 가 아니라 DROP 이므로 deferred_intent 비어있어야 함.
        self.assertIsNone(snapshot.extended.deferred_intent)
        # dance 핸들러는 최초 진입 때 딱 한 번만 호출돼야 함.
        self.assertEqual(fake_dance.call_count, 1)

        # 정상 종료: TASK_SUCCEEDED 로 IDLE 복귀.
        orchestrator.process_event(
            Event.create(
                topics.TASK_SUCCEEDED,
                "test.fake",
                payload={"task_id": "dance-1", "kind": ActionKind.DANCE.value},
            )
        )
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.IDLE)

    def test_dance_cancel_clears_timer_and_returns_idle(self) -> None:
        # 실제 dance 핸들러(_dance_execution_handler_factory)를 사용해
        # _handle_long_action_cancel 경로가 타이머를 해제하는지 확인한다.
        orchestrator = RioOrchestrator()
        _drive_to_dance_executing(orchestrator)

        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)
        self.assertIsNotNone(orchestrator._dance_timer)

        orchestrator.process_event(
            Event.create(
                topics.VOICE_ACTIVITY_STARTED,
                "test",
                payload={"synthetic": True},
            )
        )
        # EXECUTING 중 cancel 은 activity_fsm.py:53-57 에서 IDLE 로 전환.
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "system.cancel", "text": "그만"},
            )
        )

        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.IDLE)
        self.assertIsNone(orchestrator._dance_timer)

    def test_photo_locks_voice_intents_and_holds_timer_alert(self) -> None:
        orchestrator = RioOrchestrator()
        fake_photo = FakeLongRunningHandler(ActionKind.PHOTO, "photo-1")
        orchestrator.registry.register(ActionKind.PHOTO, fake_photo)

        _drive_to_photo_executing(orchestrator)
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)
        self.assertEqual(
            orchestrator.store.snapshot().extended.active_executing_kind,
            ActionKind.PHOTO,
        )

        # 다른 voice intent → DROP (deferred_intent 도 None)
        orchestrator.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "test",
                payload={"intent": "weather.current", "text": "날씨"},
            )
        )
        self.assertIsNone(orchestrator.store.snapshot().extended.deferred_intent)

        # TIMER_EXPIRED → held_alerts 에 적재, 상태는 EXECUTING 유지
        orchestrator.process_event(
            Event.create(topics.TIMER_EXPIRED, "test", payload={"label": "photo"})
        )
        self.assertEqual(len(orchestrator.held_alerts), 1)
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)

        # 완료 → IDLE 전환 후 held alert 재생되어 ALERTING 진입
        orchestrator.process_event(
            Event.create(
                topics.TASK_SUCCEEDED,
                "test.fake",
                payload={"task_id": "photo-1", "kind": ActionKind.PHOTO.value},
            )
        )
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.ALERTING)
        self.assertEqual(len(orchestrator.held_alerts), 0)

    def test_v_sign_gesture_during_dance_is_dropped_via_mapper(self) -> None:
        # gesture_mapper 는 v_sign 을 camera.capture VOICE_INTENT_DETECTED 로 변환한다.
        # dance 중에는 이 변환된 intent 가 interrupt gate 에서 DROP 되어야 한다.
        orchestrator = RioOrchestrator()
        fake_dance = FakeLongRunningHandler(ActionKind.DANCE, "dance-1")
        fake_photo = FakeLongRunningHandler(ActionKind.PHOTO, "photo-should-not-run")
        orchestrator.registry.register(ActionKind.DANCE, fake_dance)
        orchestrator.registry.register(ActionKind.PHOTO, fake_photo)

        _drive_to_dance_executing(orchestrator)
        self.assertEqual(orchestrator.store.snapshot().activity_state, ActivityState.EXECUTING)

        orchestrator.process_event(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "test",
                payload={"gesture": "v_sign"},
            )
        )

        snapshot = orchestrator.store.snapshot()
        self.assertEqual(snapshot.activity_state, ActivityState.EXECUTING)
        self.assertEqual(snapshot.extended.active_executing_kind, ActionKind.DANCE)
        self.assertEqual(fake_photo.call_count, 0)


if __name__ == "__main__":
    unittest.main()
