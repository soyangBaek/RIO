from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.app.adapters.touch.input import TouchInputAdapter, TouchSample
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events import topics
from src.app.workers.touch_worker import TouchWorker


class TouchWorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_publishes_tap_event_from_single_sample(self) -> None:
        adapter = TouchInputAdapter([TouchSample(x=10, y=20, timestamp=self.now)])
        worker = TouchWorker(bus=QueueBus(), adapter=adapter)

        events = worker.run_once(now=self.now)

        self.assertEqual(events[0].topic, topics.TOUCH_TAP_DETECTED)
        self.assertEqual(events[0].payload["x"], 10)
        self.assertEqual(events[0].payload["y"], 20)

    def test_publishes_stroke_event_from_multiple_samples(self) -> None:
        adapter = TouchInputAdapter(
            [
                TouchSample(x=10, y=10, timestamp=self.now),
                TouchSample(x=50, y=14, timestamp=self.now),
            ]
        )
        worker = TouchWorker(bus=QueueBus(), adapter=adapter)

        events = worker.run_once(now=self.now)

        self.assertEqual(events[0].topic, topics.TOUCH_STROKE_DETECTED)
        self.assertEqual(events[0].payload["path"], [(10, 10), (50, 14)])


if __name__ == "__main__":
    unittest.main()
