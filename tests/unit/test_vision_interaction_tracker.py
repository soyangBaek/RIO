from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.app.adapters.vision.interaction_tracker import VisionInteractionTracker


class VisionInteractionTrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_emits_head_left_when_face_is_on_left_side(self) -> None:
        tracker = VisionInteractionTracker()

        events = tracker.on_face_detected((0.2, 0.5), was_face_present=True, now=self.now)

        self.assertEqual([event.payload["gesture"] for event in events], ["head_left"])

    def test_emits_peekaboo_when_face_returns_quickly(self) -> None:
        tracker = VisionInteractionTracker()
        tracker.on_face_lost(now=self.now)

        events = tracker.on_face_detected((0.5, 0.5), was_face_present=False, now=self.now + timedelta(milliseconds=600))

        self.assertTrue(any(event.payload["gesture"] == "peekaboo" for event in events))


if __name__ == "__main__":
    unittest.main()
