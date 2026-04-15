from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.context_fsm import ContextThresholds, transition_context
from src.app.core.state.models import ContextState, ExtendedState


class ContextFSMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.thresholds = ContextThresholds(
            away_timeout_ms=60_000,
            idle_to_sleepy_timeout_ms=120_000,
            engaged_to_idle_timeout_ms=5_000,
            welcome_min_away_ms=3_000,
            face_lost_timeout_ms=800,
        )

    def test_away_to_idle_on_voice(self) -> None:
        event = Event.create(topics.VOICE_ACTIVITY_STARTED, "test", timestamp=self.now)
        next_state = transition_context(ContextState.AWAY, event, ExtendedState(), self.thresholds, now=self.now)
        self.assertEqual(next_state, ContextState.IDLE)

    def test_idle_to_engaged_when_face_present_and_interacting(self) -> None:
        extended = ExtendedState(face_present=True)
        event = Event.create(topics.TOUCH_TAP_DETECTED, "test", timestamp=self.now)
        next_state = transition_context(ContextState.IDLE, event, extended, self.thresholds, now=self.now)
        self.assertEqual(next_state, ContextState.ENGAGED)

    def test_engaged_to_idle_after_interaction_timeout(self) -> None:
        extended = ExtendedState(
            face_present=True,
            last_interaction_at=self.now - timedelta(seconds=6),
        )
        event = Event.create(topics.VISION_FACE_MOVED, "test", timestamp=self.now)
        next_state = transition_context(ContextState.ENGAGED, event, extended, self.thresholds, now=self.now)
        self.assertEqual(next_state, ContextState.IDLE)

    def test_idle_to_sleepy_after_long_idle(self) -> None:
        extended = ExtendedState(
            face_present=True,
            last_interaction_at=self.now - timedelta(minutes=3),
        )
        event = Event.create(topics.VISION_FACE_MOVED, "test", timestamp=self.now)
        next_state = transition_context(ContextState.IDLE, event, extended, self.thresholds, now=self.now)
        self.assertEqual(next_state, ContextState.SLEEPY)

    def test_sleepy_to_away_after_no_face_timeout(self) -> None:
        extended = ExtendedState(
            face_present=False,
            last_face_seen_at=self.now - timedelta(minutes=2),
            last_user_evidence_at=self.now - timedelta(minutes=2),
        )
        event = Event.create(topics.VISION_FACE_LOST, "test", timestamp=self.now)
        next_state = transition_context(ContextState.SLEEPY, event, extended, self.thresholds, now=self.now)
        self.assertEqual(next_state, ContextState.AWAY)


if __name__ == "__main__":
    unittest.main()
