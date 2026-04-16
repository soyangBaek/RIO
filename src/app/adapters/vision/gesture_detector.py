"""Gesture detector — Phase 2 stub.

Produces :class:`GestureResult` from a frame. MVP only exercises this
module via tests — the actual gesture repertoire (V-sign, wave, finger
gun, head direction) is scheduled for Phase 2 (prd.md). The default
implementation returns ``None``; a MediaPipe-backed variant is provided for
when Phase 2 lands.

Returned confidence and gesture name are intended to be passed straight
through to ``vision.gesture.detected``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GestureResult:
    gesture: str
    confidence: float


class GestureDetector(Protocol):
    def detect(self, frame) -> Optional[GestureResult]:
        ...


class NullGestureDetector:
    def detect(self, frame) -> Optional[GestureResult]:
        return None


class MediaPipeGestureDetector:
    """MediaPipe hand + pose-based gesture detector.

    Phase 2 fills in the actual classifier; for now it only verifies that
    mediapipe is importable so the factory can decide.
    """

    def __init__(self, min_confidence: float = 0.75) -> None:
        self._min_conf = min_confidence
        self._ready = False
        try:
            import mediapipe  # type: ignore  # noqa: F401
            self._ready = True
        except Exception as e:  # pragma: no cover
            _log.info("mediapipe gesture detector unavailable (%s)", e)

    def detect(self, frame) -> Optional[GestureResult]:  # pragma: no cover
        # Phase 2: hand-landmark → rule-based gesture classification.
        return None


def make_detector(min_confidence: float = 0.75) -> GestureDetector:
    return NullGestureDetector()  # Phase 1 baseline: no gestures yet.
