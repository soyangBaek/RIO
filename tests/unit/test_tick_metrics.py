from __future__ import annotations

import unittest

from src.app.core.safety.tick_metrics import (
    TickMetrics,
    get_active_metrics,
    increment,
    record,
    set_active_metrics,
)


class TickMetricsTest(unittest.TestCase):
    def test_records_and_summarizes_samples(self) -> None:
        metrics = TickMetrics(window=64, interval_s=5.0)
        for ms in (1.0, 2.0, 3.0, 4.0, 5.0):
            metrics.record("pump_ms", ms)
            metrics.tick_done()

        snapshot = metrics.snapshot()
        self.assertIn("pump_ms", snapshot)
        self.assertAlmostEqual(snapshot["pump_ms"]["avg"], 3.0, places=5)
        self.assertEqual(snapshot["pump_ms"]["max"], 5.0)
        self.assertEqual(snapshot["pump_ms"]["n"], 5.0)
        self.assertEqual(metrics.total_ticks, 5)

    def test_window_caps_retained_samples(self) -> None:
        metrics = TickMetrics(window=8, interval_s=0.0)
        for ms in range(20):
            metrics.record("pump_ms", float(ms))
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["pump_ms"]["n"], 8.0)
        self.assertEqual(snapshot["pump_ms"]["max"], 19.0)

    def test_maybe_log_respects_interval_via_injected_clock(self) -> None:
        metrics = TickMetrics(interval_s=2.0)
        metrics.record("pump_ms", 1.0)

        fired_first = metrics.maybe_log(now=100.0)
        self.assertFalse(fired_first)  # 첫 호출은 기준 시각만 저장.

        fired_short = metrics.maybe_log(now=101.0)
        self.assertFalse(fired_short)  # interval 미만.

        fired_ready = metrics.maybe_log(now=102.5)
        self.assertTrue(fired_ready)  # interval 경과.

        fired_again_short = metrics.maybe_log(now=103.0)
        self.assertFalse(fired_again_short)  # 직후엔 다시 미만.

    def test_maybe_log_disabled_when_interval_zero(self) -> None:
        metrics = TickMetrics(interval_s=0.0)
        metrics.record("pump_ms", 1.0)
        self.assertFalse(metrics.maybe_log(now=100.0))
        self.assertFalse(metrics.maybe_log(now=9999.0))

    def test_format_summary_without_samples(self) -> None:
        metrics = TickMetrics()
        metrics.tick_done()
        self.assertEqual(metrics.format_summary(), "ticks=1 (no samples)")

    def test_increment_counters_shown_in_summary(self) -> None:
        metrics = TickMetrics()
        metrics.increment("busy_drop")
        metrics.increment("busy_drop", by=3)
        metrics.increment("empty", by=2)
        self.assertEqual(metrics.counters(), {"busy_drop": 4, "empty": 2})
        self.assertIn("busy_drop=4", metrics.format_summary())
        self.assertIn("empty=2", metrics.format_summary())


class ModuleAccessorTest(unittest.TestCase):
    def setUp(self) -> None:
        set_active_metrics(None)

    def tearDown(self) -> None:
        set_active_metrics(None)

    def test_record_and_increment_are_noop_without_active_metrics(self) -> None:
        self.assertIsNone(get_active_metrics())
        record("asr_decode_ms", 42.0)
        increment("busy_drop")
        # 예외 없이 통과해야 한다.

    def test_set_active_metrics_wires_module_helpers(self) -> None:
        metrics = TickMetrics()
        set_active_metrics(metrics)
        record("asr_decode_ms", 12.5)
        record("asr_decode_ms", 7.5)
        increment("busy_drop", by=2)

        snap = metrics.snapshot()
        self.assertAlmostEqual(snap["asr_decode_ms"]["avg"], 10.0, places=5)
        self.assertEqual(metrics.counters()["busy_drop"], 2)

    def test_set_active_metrics_none_detaches(self) -> None:
        metrics = TickMetrics()
        set_active_metrics(metrics)
        set_active_metrics(None)
        record("asr_decode_ms", 5.0)  # no-op.
        self.assertEqual(metrics.snapshot(), {})


if __name__ == "__main__":
    unittest.main()
