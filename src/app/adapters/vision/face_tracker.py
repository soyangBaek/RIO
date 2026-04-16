"""Face frame-to-frame tracking.

Smooths the raw per-frame detections from :class:`FaceDetector` into a
stable "current face" state plus movement deltas. The vision worker uses
the output to decide when to publish:

* ``vision.face.detected`` — first time we acquire a face (or after a
  long lost period).
* ``vision.face.moved`` — when the normalized centre shifts enough, at
  most once per ``face_moved_sample_hz`` (from thresholds.yaml).
* ``vision.face.lost`` — when no detection has arrived for
  ``face_lost_timeout_ms``.

The tracker is pure and thread-agnostic — callers provide the current
detections list and ``now``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from .face_detector import FaceDetection


class TrackEvent(Enum):
    NONE = "none"
    DETECTED = "detected"
    MOVED = "moved"
    LOST = "lost"


@dataclass(frozen=True)
class FaceTrackerConfig:
    face_lost_timeout_ms: int = 800
    face_moved_sample_hz: int = 10     # max publish rate for moved
    move_epsilon: float = 0.01           # skip moves smaller than this (normalized)


@dataclass
class FaceTracker:
    config: FaceTrackerConfig = FaceTrackerConfig()
    _last_detection: Optional[FaceDetection] = None
    _last_emit_at: Optional[float] = None
    _last_seen_at: Optional[float] = None
    _present: bool = False

    def update(
        self,
        detections: List[FaceDetection],
        now: float,
    ) -> Tuple[TrackEvent, Optional[dict]]:
        """Advance tracker state. Returns ``(event, payload|None)``."""
        pick = self._pick_primary(detections)

        if pick is None:
            if not self._present:
                return TrackEvent.NONE, None
            # Decide if we should emit ``lost`` yet.
            last = self._last_seen_at
            if last is not None and (now - last) * 1000.0 < self.config.face_lost_timeout_ms:
                return TrackEvent.NONE, None
            self._present = False
            self._last_detection = None
            payload = {"last_seen_at": last if last is not None else now}
            return TrackEvent.LOST, payload

        # We have a face.
        self._last_seen_at = now
        if not self._present:
            self._present = True
            self._last_detection = pick
            self._last_emit_at = now
            return TrackEvent.DETECTED, {
                "bbox": list(pick.bbox),
                "center": list(pick.center),
                "confidence": pick.confidence,
            }

        # Tracked already — consider a moved event.
        dx = pick.center[0] - (self._last_detection.center[0] if self._last_detection else pick.center[0])
        dy = pick.center[1] - (self._last_detection.center[1] if self._last_detection else pick.center[1])
        since_emit = (now - (self._last_emit_at or 0.0)) * 1000.0
        min_interval_ms = 1000.0 / max(1, self.config.face_moved_sample_hz)
        if since_emit < min_interval_ms:
            return TrackEvent.NONE, None
        if (dx * dx + dy * dy) ** 0.5 < self.config.move_epsilon:
            return TrackEvent.NONE, None

        self._last_detection = pick
        self._last_emit_at = now
        return TrackEvent.MOVED, {
            "center": list(pick.center),
            "delta": [dx, dy],
        }

    @staticmethod
    def _pick_primary(detections: List[FaceDetection]) -> Optional[FaceDetection]:
        if not detections:
            return None
        # Pick the largest-bbox detection (closest face).
        return max(detections, key=lambda d: d.bbox[2] * d.bbox[3])
