from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.context_fsm import ContextThresholds
from src.app.core.state.models import (
    ContextState,
    OneshotName,
    RuntimeState,
)
from src.app.core.state.reducers import ReducerPipeline
from src.app.core.state.store import RuntimeStore


class WelcomeCooldownTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.thresholds = ContextThresholds(
            away_timeout_ms=60_000,
            idle_to_sleepy_timeout_ms=120_000,
            engaged_to_idle_timeout_ms=5_000,
            welcome_min_away_ms=3_000,
            welcome_cooldown_ms=10_000,
            face_lost_timeout_ms=800,
        )

    def _make_pipeline(self) -> ReducerPipeline:
        store = RuntimeStore(
            RuntimeState(
                context_state=ContextState.AWAY,
            )
        )
        # Pre-set away_started_at far enough in the past so welcome_min_away_ms is satisfied
        snapshot = store.snapshot()
        snapshot.extended.away_started_at = self.now - timedelta(seconds=30)
        store.replace(snapshot)
        return ReducerPipeline(store, thresholds=self.thresholds)

    def _face_event(self, when: datetime) -> Event:
        return Event.create(
            topics.VISION_FACE_DETECTED,
            "test",
            payload={"center": (0.5, 0.5)},
            timestamp=when,
        )

    def _face_lost_event(self, when: datetime) -> Event:
        return Event.create(topics.VISION_FACE_LOST, "test", timestamp=when)

    def test_first_reappearance_fires_welcome_and_starts_cooldown(self) -> None:
        pipeline = self._make_pipeline()
        result = pipeline.process(self._face_event(self.now))
        self.assertIsNotNone(result.triggered_oneshot)
        self.assertEqual(result.triggered_oneshot.name, OneshotName.WELCOME)
        self.assertEqual(
            result.current.extended.welcome_cooldown_until,
            self.now + timedelta(milliseconds=10_000),
        )

    def test_second_reappearance_within_cooldown_is_suppressed(self) -> None:
        pipeline = self._make_pipeline()
        pipeline.process(self._face_event(self.now))
        # Face leaves and the system goes back to AWAY
        snapshot = pipeline.store.snapshot()
        snapshot.context_state = ContextState.AWAY
        snapshot.extended.face_present = False
        snapshot.extended.away_started_at = self.now + timedelta(seconds=2)
        pipeline.store.replace(snapshot)

        # Reappear 5s after the first welcome — still inside the 10s cooldown
        second = pipeline.process(self._face_event(self.now + timedelta(seconds=5)))
        self.assertEqual(second.current.context_state, ContextState.IDLE)
        self.assertIsNone(second.triggered_oneshot)

    def test_continuous_face_presence_keeps_resetting_cooldown(self) -> None:
        pipeline = self._make_pipeline()
        pipeline.process(self._face_event(self.now))
        # Face stays present — every 1s another VISION_FACE_DETECTED arrives
        for step in range(1, 12):
            pipeline.process(self._face_event(self.now + timedelta(seconds=step)))
        # Last face_detected was at +11s; cooldown should now end at +21s
        cooldown_until = pipeline.store.snapshot().extended.welcome_cooldown_until
        self.assertEqual(
            cooldown_until,
            self.now + timedelta(seconds=11) + timedelta(milliseconds=10_000),
        )

    def test_reappearance_after_cooldown_expires_fires_again(self) -> None:
        pipeline = self._make_pipeline()
        pipeline.process(self._face_event(self.now))
        # Face leaves immediately and stays gone past the 10s cooldown
        snapshot = pipeline.store.snapshot()
        snapshot.context_state = ContextState.AWAY
        snapshot.extended.face_present = False
        snapshot.extended.away_started_at = self.now + timedelta(seconds=1)
        pipeline.store.replace(snapshot)

        later = self.now + timedelta(seconds=20)
        result = pipeline.process(self._face_event(later))
        self.assertIsNotNone(result.triggered_oneshot)
        self.assertEqual(result.triggered_oneshot.name, OneshotName.WELCOME)
        self.assertEqual(
            result.current.extended.welcome_cooldown_until,
            later + timedelta(milliseconds=10_000),
        )

    def test_peekaboo_within_cooldown_is_suppressed(self) -> None:
        pipeline = self._make_pipeline()
        # First reappear fires welcome and starts cooldown
        pipeline.process(self._face_event(self.now))

        # Quick face-lost then peekaboo gesture 1s later (still inside 10s cooldown)
        peekaboo = Event.create(
            topics.VISION_GESTURE_DETECTED,
            "test",
            payload={"gesture": "peekaboo", "confidence": 1.0},
            timestamp=self.now + timedelta(seconds=1),
        )
        result = pipeline.process(peekaboo)
        self.assertIsNone(result.triggered_oneshot)

    def test_peekaboo_after_cooldown_fires_and_renews_cooldown(self) -> None:
        pipeline = self._make_pipeline()
        pipeline.process(self._face_event(self.now))

        # Wait past the cooldown without any face events resetting it
        snapshot = pipeline.store.snapshot()
        snapshot.extended.welcome_cooldown_until = self.now  # already expired by next event
        pipeline.store.replace(snapshot)

        later = self.now + timedelta(seconds=15)
        peekaboo = Event.create(
            topics.VISION_GESTURE_DETECTED,
            "test",
            payload={"gesture": "peekaboo", "confidence": 1.0},
            timestamp=later,
        )
        result = pipeline.process(peekaboo)
        self.assertIsNotNone(result.triggered_oneshot)
        self.assertEqual(result.triggered_oneshot.name, OneshotName.WELCOME)
        self.assertEqual(
            result.current.extended.welcome_cooldown_until,
            later + timedelta(milliseconds=10_000),
        )

    def test_wave_gesture_welcome_does_not_set_cooldown(self) -> None:
        pipeline = self._make_pipeline()
        # Move into IDLE first so wave isn't competing with reappear logic
        snapshot = pipeline.store.snapshot()
        snapshot.context_state = ContextState.IDLE
        snapshot.extended.face_present = True
        snapshot.extended.away_started_at = None
        pipeline.store.replace(snapshot)

        wave = Event.create(
            topics.VISION_GESTURE_DETECTED,
            "test",
            payload={"gesture": "wave", "confidence": 1.0},
            timestamp=self.now,
        )
        result = pipeline.process(wave)
        self.assertIsNotNone(result.triggered_oneshot)
        self.assertEqual(result.triggered_oneshot.name, OneshotName.WELCOME)
        self.assertIsNone(result.current.extended.welcome_cooldown_until)


if __name__ == "__main__":
    unittest.main()
