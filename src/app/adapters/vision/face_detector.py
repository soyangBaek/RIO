"""Face detector.

MediaPipe is the default backend (fast on RPi 4+, built-in tracker). An
OpenCV DNN path is provided as a fallback for environments where
mediapipe is unavailable, and a null detector for dev hosts without either.

Returned detections are in the normalized-coordinate contract from
architecture.md §6.4: ``bbox = [x, y, w, h]`` and ``center = [x, y]`` all in
``[0, 1]``, with origin at the camera frame's top-left.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Protocol

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaceDetection:
    bbox: tuple  # (x, y, w, h) in [0, 1]
    center: tuple  # (x, y) in [0, 1]
    confidence: float


class FaceDetector(Protocol):
    def detect(self, frame) -> List[FaceDetection]:
        ...


class NullFaceDetector:
    def detect(self, frame) -> List[FaceDetection]:
        return []


class MediaPipeFaceDetector:
    """MediaPipe-backed detector. Lazily initialised; returns ``[]`` if
    mediapipe is not importable so callers do not crash at boot."""

    def __init__(self, min_confidence: float = 0.6, model_selection: int = 0) -> None:
        self._min_conf = min_confidence
        self._detector = None
        try:
            import mediapipe as mp  # type: ignore
            self._detector = mp.solutions.face_detection.FaceDetection(
                model_selection=model_selection,
                min_detection_confidence=min_confidence,
            )
        except Exception as e:  # pragma: no cover
            _log.warning("mediapipe unavailable (%s); face detector disabled", e)
            self._detector = None

    def detect(self, frame) -> List[FaceDetection]:  # pragma: no cover - env dep
        if self._detector is None or frame is None:
            return []
        try:
            import cv2  # type: ignore
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._detector.process(rgb)
            if not result.detections:
                return []
            out: List[FaceDetection] = []
            for det in result.detections:
                rel = det.location_data.relative_bounding_box
                if det.score and det.score[0] < self._min_conf:
                    continue
                bbox = (float(rel.xmin), float(rel.ymin),
                        float(rel.width), float(rel.height))
                cx = bbox[0] + bbox[2] / 2.0
                cy = bbox[1] + bbox[3] / 2.0
                conf = float(det.score[0]) if det.score else 0.0
                out.append(FaceDetection(bbox=bbox, center=(cx, cy), confidence=conf))
            return out
        except Exception:
            _log.exception("mediapipe face detect failed")
            return []


def make_detector(min_confidence: float = 0.6) -> FaceDetector:
    try:
        mp = MediaPipeFaceDetector(min_confidence=min_confidence)
        if mp._detector is not None:
            return mp
    except Exception:  # pragma: no cover
        pass
    return NullFaceDetector()
