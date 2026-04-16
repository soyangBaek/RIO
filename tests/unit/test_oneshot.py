"""T-061: Oneshot 중첩 정책 테스트.

state-machine.md §5.1 기준.
"""
import sys
import time
import unittest

sys.path.insert(0, ".")

from src.app.core.state.models import OneshotName
from src.app.core.state.oneshot import try_trigger_oneshot, expire_oneshot_if_done
from src.app.core.state.store import ActiveOneshot, Store

DEFAULT_CONFIG = {}


class TestOneshot(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.config = DEFAULT_CONFIG

    def test_trigger_when_empty(self):
        result = try_trigger_oneshot(self.store, OneshotName.STARTLED, self.config)
        self.assertTrue(result)
        self.assertIsNotNone(self.store.active_oneshot)
        self.assertEqual(self.store.active_oneshot.name, OneshotName.STARTLED)

    def test_higher_priority_preempts(self):
        """Priority preempt: startled(30) > welcome(20)."""
        try_trigger_oneshot(self.store, OneshotName.WELCOME, self.config)
        self.assertEqual(self.store.active_oneshot.name, OneshotName.WELCOME)

        result = try_trigger_oneshot(self.store, OneshotName.STARTLED, self.config)
        self.assertTrue(result)
        self.assertEqual(self.store.active_oneshot.name, OneshotName.STARTLED)

    def test_lower_priority_dropped(self):
        """Lower priority drop."""
        try_trigger_oneshot(self.store, OneshotName.STARTLED, self.config)
        result = try_trigger_oneshot(self.store, OneshotName.WELCOME, self.config)
        self.assertFalse(result)
        self.assertEqual(self.store.active_oneshot.name, OneshotName.STARTLED)

    def test_same_priority_coalesces(self):
        """Same priority: 새 이벤트 무시 (깜빡임 방지)."""
        try_trigger_oneshot(self.store, OneshotName.WELCOME, self.config)
        result = try_trigger_oneshot(self.store, OneshotName.HAPPY, self.config)
        self.assertFalse(result)  # same priority (20) → ignore
        self.assertEqual(self.store.active_oneshot.name, OneshotName.WELCOME)

    def test_same_priority_replace_at_80_percent(self):
        """80% 이상 경과 시 같은 priority도 교체."""
        try_trigger_oneshot(self.store, OneshotName.WELCOME, self.config)
        # 강제로 80% 이상 경과 시뮬레이션
        self.store.active_oneshot = ActiveOneshot(
            name=OneshotName.WELCOME,
            priority=20,
            started_at=time.time() - 1.3,  # 1.3s ago, duration 1.5s → ~87%
            duration_ms=1500,
        )
        result = try_trigger_oneshot(self.store, OneshotName.HAPPY, self.config)
        self.assertTrue(result)
        self.assertEqual(self.store.active_oneshot.name, OneshotName.HAPPY)

    def test_expired_oneshot_cleanup(self):
        """만료된 oneshot 자동 정리."""
        self.store.active_oneshot = ActiveOneshot(
            name=OneshotName.STARTLED,
            priority=30,
            started_at=time.time() - 5,  # 5초 전
            duration_ms=600,
        )
        expired = expire_oneshot_if_done(self.store)
        self.assertEqual(expired, OneshotName.STARTLED)
        self.assertIsNone(self.store.active_oneshot)


if __name__ == "__main__":
    unittest.main()
