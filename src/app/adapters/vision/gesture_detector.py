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
    def _detect_heart(hand_landmarks: list[Any]) -> dict | None:
        """두 손이 하트 모양을 만들고 있으면 metric dict 을 반환, 아니면 None.

        판정 조건 (모두 만족해야 통과):
          (1) 엄지끝끼리 가까움 (거리 < 손바닥 크기 × touch_ratio)
          (2) 검지끝끼리 가까움
          (3) 엄지가 검지보다 아래쪽 = 하트 실루엣 방향
          (4) 양손의 중지·약지·소지는 모두 curl (C 곡선 강제) —
              펼친 양손으로 엄지검지만 맞붙이는 케이스 배제
          (5) 좌/우 손이 화면상 양쪽으로 충분히 벌어지고, 손가락 만나는
              중심점이 두 손목 x 사이에 위치 — 한쪽 팔로만 만드는 모양 배제
          (6) 검지끝 평균이 검지 PIP 평균보다 아래 (하트 윗부분 골짜기) —
              손이 단순히 V/일자로 모인 게 아니라 각 손이 C 를 그리는지 검증

        "가까움" 기준 거리는 손-카메라 거리에 따라 절대값이 달라지므로
        손바닥 크기(wrist↔middle MCP) 비율로 계산한다.
        """
        if len(hand_landmarks) < 2:
            return None

        def _dist(a: Any, b: Any) -> float:
            dx = float(a.x) - float(b.x)
            dy = float(a.y) - float(b.y)
            return (dx * dx + dy * dy) ** 0.5

        def _is_extended(tip: Any, pip: Any, mcp: Any) -> bool:
            return float(tip.y) < float(pip.y) < float(mcp.y)

        def _hand_curled(lm: Any) -> bool:
            # 중지/약지/소지 모두 extended 가 아니어야 C 곡선으로 본다.
            return (
                not _is_extended(lm[12], lm[10], lm[9])
                and not _is_extended(lm[16], lm[14], lm[13])
                and not _is_extended(lm[20], lm[18], lm[17])
            )

        # 화면 좌/우 기준으로 정렬 (왼손=a, 오른손=b).
        sorted_hands = sorted(hand_landmarks[:2], key=lambda lm: float(lm[0].x))
        a, b = sorted_hands[0], sorted_hands[1]

        hand_span = (_dist(a[0], a[9]) + _dist(b[0], b[9])) / 2.0
        if hand_span <= 1e-6:
            return None

        thumb_dist = _dist(a[4], b[4])
        index_dist = _dist(a[8], b[8])
        mid_thumb_y = (float(a[4].y) + float(b[4].y)) / 2.0
        mid_index_y = (float(a[8].y) + float(b[8].y)) / 2.0
        mid_index_pip_y = (float(a[6].y) + float(b[6].y)) / 2.0

        touch_ratio = 0.75
        thumbs_meet = thumb_dist < hand_span * touch_ratio
        indices_meet = index_dist < hand_span * touch_ratio
        orientation_ok = mid_thumb_y > mid_index_y
        fingers_curled = _hand_curled(a) and _hand_curled(b)

        # 좌/우 손 벌어짐: 두 손목 x 간격이 손바닥 크기 대비 충분해야 한다.
        lateral_gap = float(b[0].x) - float(a[0].x)
        hands_apart = lateral_gap > hand_span * 0.3
        # 만나는 지점(엄지끝 평균 x)이 두 손목 x 사이에 있어야 "대칭".
        meet_x = (float(a[4].x) + float(b[4].x)) / 2.0
        symmetric = float(a[0].x) < meet_x < float(b[0].x)

        # 하트 윗부분 골짜기: 검지끝이 PIP 보다 아래쪽(큰 y).
        top_valley = mid_index_y >= mid_index_pip_y

        metrics = {
            "thumb_dist": thumb_dist,
            "index_dist": index_dist,
            "hand_span": hand_span,
            "lateral_gap": lateral_gap,
            "thumbs_meet": thumbs_meet,
            "indices_meet": indices_meet,
            "heart_shape": orientation_ok,
            "fingers_curled": fingers_curled,
            "hands_apart": hands_apart,
            "symmetric": symmetric,
            "top_valley": top_valley,
        }
        if (
            thumbs_meet
            and indices_meet
            and orientation_ok
            and fingers_curled
            and hands_apart
            and symmetric
            and top_valley
        ):
            return metrics
        return None

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

            # Heart gesture: 양손이 하트 모양을 만들 때.
            # 엄지끼리 아래에서 만나고 검지끼리 위에서 만나 C+C 가
            # 합쳐진 하트 실루엣을 형성하는 K-pop 스타일 양손 하트.
            if len(result.multi_hand_landmarks) >= 2:
                heart = self._detect_heart(
                    [hand.landmark for hand in result.multi_hand_landmarks[:2]]
                )
                if heart is not None:
                    gesture = "heart"
                    debug["classified"] = gesture
                    debug["heart_metrics"] = heart
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
