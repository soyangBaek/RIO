"""T-043: 제스처 검출기.

MediaPipe Hands / 고개 방향 기반. 손총, V자, 손 흔들기 등.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)


class GestureDetector:
    """손동작/고개 제스처 검출."""

    def __init__(self, min_confidence: float = 0.75, headless: bool = False) -> None:
        self._min_confidence = min_confidence
        self._headless = headless
        self._hands = None
        self._last_gesture_at: float = 0
        self._cooldown = 1.0  # 같은 제스처 1초 쿨다운

    def initialize(self) -> None:
        if self._headless:
            return
        try:
            import mediapipe as mp
            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=self._min_confidence,
                min_tracking_confidence=0.5,
            )
            logger.info("GestureDetector: MediaPipe Hands initialized")
        except ImportError:
            logger.warning("MediaPipe not available – gesture detection disabled")

    def detect(self, frame: Any) -> List[Event]:
        """프레임에서 제스처 검출 → 이벤트 목록."""
        if self._headless or self._hands is None:
            return []

        now = time.time()
        if now - self._last_gesture_at < self._cooldown:
            return []

        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)

            if not results.multi_hand_landmarks:
                return []

            for hand_landmarks in results.multi_hand_landmarks:
                gesture = self._classify_gesture(hand_landmarks)
                if gesture:
                    self._last_gesture_at = now
                    return [Event(
                        topic=Topics.VISION_GESTURE_DETECTED,
                        source="vision_worker",
                        payload={
                            "gesture": gesture,
                            "confidence": self._min_confidence,
                        },
                        timestamp=now,
                    )]
        except Exception as e:
            logger.debug("Gesture detect error: %s", e)

        return []

    def _classify_gesture(self, landmarks: Any) -> Optional[str]:
        """간단한 제스처 분류 (확장 가능)."""
        try:
            lm = landmarks.landmark
            # V sign: index + middle up, others down
            index_up = lm[8].y < lm[6].y
            middle_up = lm[12].y < lm[10].y
            ring_down = lm[16].y > lm[14].y
            pinky_down = lm[20].y > lm[18].y
            thumb_down = lm[4].y > lm[3].y

            if index_up and middle_up and ring_down and pinky_down:
                return "v_sign"

            # Open palm (wave)
            if all(lm[tip].y < lm[tip - 2].y for tip in [8, 12, 16, 20]):
                return "open_palm"

            # Thumbs up
            if lm[4].y < lm[3].y < lm[2].y and ring_down and pinky_down:
                return "thumbs_up"

        except Exception:
            pass
        return None

    def shutdown(self) -> None:
        if self._hands:
            try:
                self._hands.close()
            except Exception:
                pass
