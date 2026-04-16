"""T-042: 얼굴 추적기 – 연속 프레임 간 얼굴 동일성 + center delta 계산.

face_detector 결과를 받아 face.detected / face.lost / face.moved 이벤트 생성.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.app.adapters.vision.face_detector import FaceDetection
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)


class FaceTracker:
    """얼굴 추적 – detected/lost/moved 이벤트 생성."""

    def __init__(
        self,
        lost_timeout_ms: float = 800,
        sample_hz: float = 10,
    ) -> None:
        self._lost_timeout_ms = lost_timeout_ms
        self._sample_interval = 1.0 / sample_hz if sample_hz > 0 else 0.1
        self._face_present = False
        self._last_center: Optional[List[float]] = None
        self._last_seen_at: float = 0
        self._last_moved_at: float = 0

    def update(self, detections: List[FaceDetection]) -> List[Event]:
        """검출 결과 → 이벤트 목록."""
        now = time.time()
        events: List[Event] = []

        if detections:
            best = max(detections, key=lambda d: d.confidence)
            center = best.center

            if not self._face_present:
                # face.detected
                self._face_present = True
                events.append(Event(
                    topic=Topics.VISION_FACE_DETECTED,
                    source="vision_worker",
                    payload={
                        "bbox": best.bbox,
                        "center": center,
                        "confidence": best.confidence,
                    },
                    timestamp=now,
                ))
                self._last_center = center

            # face.moved (샘플링)
            if self._last_center and (now - self._last_moved_at) >= self._sample_interval:
                delta = [
                    center[0] - self._last_center[0],
                    center[1] - self._last_center[1],
                ]
                if abs(delta[0]) > 0.005 or abs(delta[1]) > 0.005:
                    events.append(Event(
                        topic=Topics.VISION_FACE_MOVED,
                        source="vision_worker",
                        payload={"center": center, "delta": delta},
                        timestamp=now,
                    ))
                    self._last_moved_at = now

            self._last_center = center
            self._last_seen_at = now

        else:
            # 얼굴 미검출
            if self._face_present:
                elapsed_ms = (now - self._last_seen_at) * 1000
                if elapsed_ms >= self._lost_timeout_ms:
                    self._face_present = False
                    events.append(Event(
                        topic=Topics.VISION_FACE_LOST,
                        source="vision_worker",
                        payload={"last_seen_at": self._last_seen_at},
                        timestamp=now,
                    ))
                    self._last_center = None

        return events

    @property
    def is_tracking(self) -> bool:
        return self._face_present
