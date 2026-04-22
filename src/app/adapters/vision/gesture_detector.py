from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.safety.tick_metrics import record as record_metric


@dataclass(slots=True)
class GestureDetector:
    confidence_min: float = 0.75
    emit_cooldown_seconds: float = 8.0
    _hands: Any = field(default=None, init=False, repr=False)
    _last_gesture: str | None = field(default=None, init=False, repr=False)
    _last_emitted_at: datetime | None = field(default=None, init=False, repr=False)
    _last_debug: dict = field(default_factory=dict, init=False, repr=False)

    def _ensure_hands(self) -> Any:
        if self._hands is not None:
            return self._hands
        import mediapipe as mp

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=self.confidence_min,
            min_tracking_confidence=self.confidence_min,
        )
        return self._hands

    @staticmethod
    def _is_extended(tip: Any, pip: Any, mcp: Any) -> bool:
        return tip.y < pip.y < mcp.y

    @staticmethod
    def _thumb_extended(lm: Any) -> bool:
        wrist, mcp, ip, tip = lm[0], lm[2], lm[3], lm[4]
        v1x, v1y = mcp.x - wrist.x, mcp.y - wrist.y
        v2x, v2y = tip.x - ip.x, tip.y - ip.y
        dot = v1x * v2x + v1y * v2y
        n1 = (v1x * v1x + v1y * v1y) ** 0.5
        n2 = (v2x * v2x + v2y * v2y) ** 0.5
        if n1 < 1e-6 or n2 < 1e-6:
            return False
        cos_angle = dot / (n1 * n2)
        tip_far = (
            ((tip.x - mcp.x) ** 2 + (tip.y - mcp.y) ** 2) ** 0.5
            > ((ip.x - mcp.x) ** 2 + (ip.y - mcp.y) ** 2) ** 0.5
        )
        return cos_angle > 0.5 and tip_far

    @staticmethod
    def _palm_facing_camera(lm: Any, handedness_label: str | None) -> bool:
        thumb_x = lm[4].x
        pinky_mcp_x = lm[17].x
        if handedness_label == "Right":
            return thumb_x < pinky_mcp_x
        if handedness_label == "Left":
            return thumb_x > pinky_mcp_x
        return False

    def _classify_hand(
        self,
        hand_landmarks: Any,
        handedness_label: str | None = None,
        face_center: tuple[float, float] | None = None,
    ) -> tuple[str | None, dict]:
        lm = hand_landmarks.landmark
        thumb_extended = self._thumb_extended(lm)
        index_up = self._is_extended(lm[8], lm[6], lm[5])
        middle_up = self._is_extended(lm[12], lm[10], lm[9])
        ring_up = self._is_extended(lm[16], lm[14], lm[13])
        pinky_up = self._is_extended(lm[20], lm[18], lm[17])
        palm_facing = self._palm_facing_camera(lm, handedness_label)

        wrist_y = float(lm[0].y)
        hand_above_face = (
            face_center is not None and wrist_y < float(face_center[1])
        )

        fingers = {
            "thumb": bool(thumb_extended),
            "index": bool(index_up),
            "middle": bool(middle_up),
            "ring": bool(ring_up),
            "pinky": bool(pinky_up),
        }

        gesture: str | None = None
        if thumb_extended and index_up and not middle_up and not ring_up and not pinky_up:
            gesture = "finger_gun"
        elif index_up and middle_up and not ring_up and not pinky_up and palm_facing:
            gesture = "v_sign"
        elif index_up and middle_up and ring_up and pinky_up:
            gesture = "wave"
        elif not index_up and not middle_up and not ring_up and not pinky_up:
            # fist는 얼굴 위로 주먹을 올렸을 때만 인정. 책상 위에 손이 놓인
            # 상태처럼 우연히 주먹 모양이 잡히는 케이스를 배제하기 위함.
            if hand_above_face:
                gesture = "fist"
        elif index_up and not middle_up and not ring_up and not pinky_up:
            gesture = "point"

        return gesture, {
            "fingers": fingers,
            "palm_facing": palm_facing,
            "wrist_y": wrist_y,
            "hand_above_face": hand_above_face,
        }

    def _cooldown_ready(self, gesture: str, when: datetime) -> bool:
        if self._last_gesture != gesture or self._last_emitted_at is None:
            return True
        age = (when - self._last_emitted_at).total_seconds()
        return age >= self.emit_cooldown_seconds

    def _cooldown_remaining(self, gesture: str | None, when: datetime) -> float:
        if gesture is None or self._last_emitted_at is None or self._last_gesture != gesture:
            return 0.0
        age = (when - self._last_emitted_at).total_seconds()
        remain = self.emit_cooldown_seconds - age
        return remain if remain > 0 else 0.0

    def inspect(self) -> dict:
        return dict(self._last_debug)

    def detect(
        self,
        frame: Any,
        *,
        trace_id: str | None = None,
        now: datetime | None = None,
        rgb_frame: Any | None = None,
        face_center: tuple[float, float] | None = None,
    ) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        debug: dict = {
            "hand_present": False,
            "fingers": None,
            "handedness": None,
            "palm_facing": False,
            "classified": None,
            "confidence": 0.0,
            "emitted": False,
            "cooldown_remaining": 0.0,
            "hand_above_face": False,
        }

        if not isinstance(frame, dict):
            hands = self._ensure_hands()
            if rgb_frame is None:
                import cv2

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                rgb = rgb_frame
            t0 = time.perf_counter()
            result = hands.process(rgb)
            record_metric("gesture_detect_ms", (time.perf_counter() - t0) * 1000.0)
            if not result.multi_hand_landmarks:
                self._last_debug = debug
                return []
            debug["hand_present"] = True

            # Check for both_palms: two hands, both palms facing camera
            if len(result.multi_hand_landmarks) >= 2:
                both_facing = True
                for i in range(2):
                    h_label = None
                    if result.multi_handedness:
                        try:
                            h_label = result.multi_handedness[i].classification[0].label
                        except (AttributeError, IndexError):
                            pass
                    if not self._palm_facing_camera(result.multi_hand_landmarks[i].landmark, h_label):
                        both_facing = False
                        break
                if both_facing:
                    gesture = "both_palms"
                    debug["classified"] = gesture
                    confidence = 1.0
                    # skip single-hand classification
                    self._last_debug = debug
                    if confidence >= self.confidence_min and self._cooldown_ready(gesture, when):
                        self._last_gesture = gesture
                        self._last_emitted_at = when
                        debug["emitted"] = True
                        debug["cooldown_remaining"] = self.emit_cooldown_seconds
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
                    return []

            landmarks = result.multi_hand_landmarks[0]
            handedness_label: str | None = None
            if result.multi_handedness:
                try:
                    handedness_label = result.multi_handedness[0].classification[0].label
                except (AttributeError, IndexError):
                    handedness_label = None
            debug["handedness"] = handedness_label
            gesture, extra = self._classify_hand(
                landmarks,
                handedness_label,
                face_center=face_center,
            )
            debug["fingers"] = extra["fingers"]
            debug["palm_facing"] = extra["palm_facing"]
            debug["hand_above_face"] = extra.get("hand_above_face", False)
            debug["classified"] = gesture
            confidence = 1.0 if gesture else 0.0
        else:
            gesture = frame.get("gesture")
            confidence = float(frame.get("gesture_confidence", 0.0))
            if gesture == "open_palm":
                gesture = "wave"
            # Dict-frame 경로에서도 fist는 얼굴 위 조건을 요구.
            if gesture == "fist":
                wrist_y = frame.get("wrist_y")
                face_y = face_center[1] if face_center is not None else None
                if wrist_y is None or face_y is None or float(wrist_y) >= float(face_y):
                    gesture = None
            debug["hand_present"] = gesture is not None
            debug["classified"] = gesture

        debug["confidence"] = confidence
        debug["cooldown_remaining"] = self._cooldown_remaining(gesture, when)

        if gesture and confidence >= self.confidence_min and self._cooldown_ready(str(gesture), when):
            self._last_gesture = str(gesture)
            self._last_emitted_at = when
            debug["emitted"] = True
            debug["cooldown_remaining"] = self.emit_cooldown_seconds
            self._last_debug = debug
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
        self._last_debug = debug
        return []
