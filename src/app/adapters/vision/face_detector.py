"""T-041: 얼굴 검출기.

MediaPipe FaceDetection 기반. normalized coordinates 출력.
architecture.md §6.4 좌표 규격.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FaceDetection:
    """검출된 얼굴 정보 (normalized coords)."""
    bbox: list  # [x, y, w, h] normalized 0.0~1.0
    center: list  # [x, y] normalized
    confidence: float
    timestamp: float


class FaceDetector:
    """얼굴 검출기. MediaPipe 또는 OpenCV cascade fallback."""

    def __init__(self, min_confidence: float = 0.6, headless: bool = False) -> None:
        self._min_confidence = min_confidence
        self._headless = headless
        self._detector = None
        self._backend = "none"

    def initialize(self) -> None:
        if self._headless:
            return

        # MediaPipe 우선
        try:
            import mediapipe as mp
            self._detector = mp.solutions.face_detection.FaceDetection(
                min_detection_confidence=self._min_confidence,
                model_selection=0,  # short-range
            )
            self._backend = "mediapipe"
            logger.info("FaceDetector: MediaPipe initialized")
            return
        except ImportError:
            pass

        # OpenCV cascade fallback
        try:
            import cv2
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._detector = cv2.CascadeClassifier(cascade_path)
            self._backend = "opencv"
            logger.info("FaceDetector: OpenCV cascade initialized")
            return
        except Exception:
            pass

        logger.warning("FaceDetector: no backend available")

    def detect(self, frame: Any) -> List[FaceDetection]:
        """프레임에서 얼굴 검출. normalized coordinates 반환."""
        if self._headless or self._detector is None:
            return []

        now = time.time()

        if self._backend == "mediapipe":
            return self._detect_mediapipe(frame, now)
        elif self._backend == "opencv":
            return self._detect_opencv(frame, now)
        return []

    def _detect_mediapipe(self, frame: Any, now: float) -> List[FaceDetection]:
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._detector.process(rgb)

            if not results.detections:
                return []

            faces = []
            for det in results.detections:
                bb = det.location_data.relative_bounding_box
                x, y, w, h = bb.xmin, bb.ymin, bb.width, bb.height
                cx, cy = x + w / 2, y + h / 2
                conf = det.score[0] if det.score else 0.0

                if conf >= self._min_confidence:
                    faces.append(FaceDetection(
                        bbox=[x, y, w, h],
                        center=[cx, cy],
                        confidence=conf,
                        timestamp=now,
                    ))
            return faces
        except Exception as e:
            logger.debug("MediaPipe detect error: %s", e)
            return []

    def _detect_opencv(self, frame: Any, now: float) -> List[FaceDetection]:
        try:
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            rects = self._detector.detectMultiScale(gray, 1.1, 4)

            faces = []
            for (rx, ry, rw, rh) in rects:
                nx, ny = rx / w, ry / h
                nw, nh = rw / w, rh / h
                cx, cy = nx + nw / 2, ny + nh / 2
                faces.append(FaceDetection(
                    bbox=[nx, ny, nw, nh],
                    center=[cx, cy],
                    confidence=0.8,
                    timestamp=now,
                ))
            return faces
        except Exception as e:
            logger.debug("OpenCV detect error: %s", e)
            return []

    def shutdown(self) -> None:
        if self._backend == "mediapipe" and self._detector:
            try:
                self._detector.close()
            except Exception:
                pass
