from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.app.core.state.models import OneshotName
from src.app.core.state.oneshot import OneshotDispatcher


class OneshotDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.dispatcher = OneshotDispatcher()

    def test_priority_preempts_active(self) -> None:
        active = self.dispatcher.build(OneshotName.WELCOME, self.now)
        decision = self.dispatcher.trigger(active, OneshotName.STARTLED, self.now)
        self.assertTrue(decision.changed)
        self.assertEqual(decision.active.name, OneshotName.STARTLED)

    def test_lower_priority_drops(self) -> None:
        active = self.dispatcher.build(OneshotName.STARTLED, self.now)
        decision = self.dispatcher.trigger(active, OneshotName.WELCOME, self.now)
        self.assertFalse(decision.changed)
        self.assertEqual(decision.active.name, OneshotName.STARTLED)

    def test_same_priority_coalesces_before_80_percent(self) -> None:
        active = self.dispatcher.build(OneshotName.HAPPY, self.now)
        decision = self.dispatcher.trigger(active, OneshotName.WELCOME, self.now + timedelta(milliseconds=100))
        self.assertFalse(decision.changed)
        self.assertEqual(decision.active.name, OneshotName.HAPPY)

    def test_same_priority_replaces_after_80_percent(self) -> None:
        active = self.dispatcher.build(OneshotName.HAPPY, self.now)
        decision = self.dispatcher.trigger(active, OneshotName.WELCOME, self.now + timedelta(milliseconds=900))
        self.assertTrue(decision.changed)
        self.assertEqual(decision.active.name, OneshotName.WELCOME)

    def test_expire_returns_none(self) -> None:
        active = self.dispatcher.build(OneshotName.CONFUSED, self.now)
        expired = self.dispatcher.expire(active, self.now + timedelta(seconds=1))
        self.assertIsNone(expired)


if __name__ == "__main__":
    unittest.main()
