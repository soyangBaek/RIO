from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class GestureDetector:
    confidence_min: float = 0.75
    emit_cooldown_seconds: float = 0.75
    _hands: Any = field(default=None, init=False, repr=False)
    _last_gesture: str | None = field(default=None, init=False, repr=False)
    _last_emitted_at: datetime | None = field(default=None, init=False, repr=False)

    def _ensure_hands(self) -> Any:
        if self._hands is not None:
            return self._hands
        import mediapipe as mp

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=self.confidence_min,
            min_tracking_confidence=self.confidence_min,
        )
        return self._hands

    @staticmethod
    def _is_extended(tip: Any, pip: Any, mcp: Any) -> bool:
        return tip.y < pip.y < mcp.y

    def _classify_hand(self, hand_landmarks: Any) -> str | None:
        lm = hand_landmarks.landmark
        thumb_extended = abs(lm[4].x - lm[2].x) >= 0.08
        index_up = self._is_extended(lm[8], lm[6], lm[5])
        middle_up = self._is_extended(lm[12], lm[10], lm[9])
        ring_up = self._is_extended(lm[16], lm[14], lm[13])
        pinky_up = self._is_extended(lm[20], lm[18], lm[17])

        if thumb_extended and index_up and not middle_up and not ring_up and not pinky_up:
            return "finger_gun"
        if index_up and middle_up and not ring_up and not pinky_up:
            return "v_sign"
        if index_up and middle_up and ring_up and pinky_up:
            return "wave"
        if index_up and not middle_up and not ring_up and not pinky_up:
            return "point"
        return None

    def _cooldown_ready(self, gesture: str, when: datetime) -> bool:
        if self._last_gesture != gesture or self._last_emitted_at is None:
            return True
        age = (when - self._last_emitted_at).total_seconds()
        return age >= self.emit_cooldown_seconds

    def detect(self, frame: Any, *, trace_id: str | None = None, now: datetime | None = None) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        if not isinstance(frame, dict):
            hands = self._ensure_hands()
            import cv2

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
            if not result.multi_hand_landmarks:
                self._last_gesture = None
                return []
            landmarks = result.multi_hand_landmarks[0]
            gesture = self._classify_hand(landmarks)
            confidence = 1.0 if gesture else 0.0
        else:
            gesture = frame.get("gesture")
            confidence = float(frame.get("gesture_confidence", 0.0))
            if gesture == "open_palm":
                gesture = "wave"

        if gesture and confidence >= self.confidence_min and self._cooldown_ready(str(gesture), when):
            self._last_gesture = str(gesture)
            self._last_emitted_at = when
            return [
                Event.create(
                    topics.VISION_GESTURE_DETECTED,
                    "vision.gesture_detector",
                    payload={"gesture": gesture, "confidence": confidence},
                    confidence=confidence,
                    trace_id=trace_id,
                    timestamp=when,
                )
            ]
        if not gesture:
            self._last_gesture = None
        return []
