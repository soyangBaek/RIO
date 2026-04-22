from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from src.app.adapters.vision.gesture_detector import GestureDetector


@dataclass
class _Landmark:
    x: float
    y: float
    z: float = 0.0


class _HandLandmarks:
    """Mediapipe의 hand_landmarks.landmark 와 동일한 인덱스 접근을 흉내 낸다."""

    def __init__(self, landmarks: list[_Landmark]) -> None:
        self.landmark = landmarks


def _fist_landmarks(wrist_y: float) -> _HandLandmarks:
    """모든 손가락이 접힌 주먹 모양. wrist.y 만 파라미터로 지정."""
    # 핵심 인덱스: 0(wrist), 5/6/8(index mcp/pip/tip),
    # 9/10/12(middle), 13/14/16(ring), 17/18/20(pinky),
    # 2/3/4(thumb wrist-side/ip/tip)
    data = [_Landmark(0.5, wrist_y) for _ in range(21)]

    # 각 손가락이 접힌 상태: tip.y >= pip.y >= mcp.y 가 되도록 세팅
    #  (_is_extended 는 tip.y < pip.y < mcp.y 일 때만 True)
    # wrist 아래쪽(=y 가 더 큼)으로 손가락이 있다고 가정.
    for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 17), (17, 18, 20)):
        data[mcp] = _Landmark(0.5, wrist_y + 0.05)
        data[pip] = _Landmark(0.5, wrist_y + 0.08)
        data[tip] = _Landmark(0.5, wrist_y + 0.10)

    # Thumb: 접힌 형태 (mcp 와 tip 이 가까움)
    data[0] = _Landmark(0.5, wrist_y)
    data[2] = _Landmark(0.5, wrist_y + 0.02)
    data[3] = _Landmark(0.5, wrist_y + 0.03)
    data[4] = _Landmark(0.5, wrist_y + 0.04)
    return _HandLandmarks(data)


class GestureDetectorFistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = GestureDetector()
        self.now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)

    def test_fist_ignored_when_no_face(self) -> None:
        gesture, _extra = self.detector._classify_hand(
            _fist_landmarks(wrist_y=0.2),
            handedness_label=None,
            face_center=None,
        )
        self.assertIsNone(gesture)

    def test_fist_ignored_when_hand_below_face(self) -> None:
        # 얼굴 중심 y=0.4, 손목 y=0.7 → 손이 얼굴 아래 → fist 무시
        gesture, extra = self.detector._classify_hand(
            _fist_landmarks(wrist_y=0.7),
            handedness_label=None,
            face_center=(0.5, 0.4),
        )
        self.assertIsNone(gesture)
        self.assertFalse(extra["hand_above_face"])

    def test_fist_detected_when_hand_above_face(self) -> None:
        # 얼굴 중심 y=0.5, 손목 y=0.2 → 손이 얼굴 위 → fist 인정
        gesture, extra = self.detector._classify_hand(
            _fist_landmarks(wrist_y=0.2),
            handedness_label=None,
            face_center=(0.5, 0.5),
        )
        self.assertEqual(gesture, "fist")
        self.assertTrue(extra["hand_above_face"])

    def test_dict_frame_fist_requires_face_and_wrist_above(self) -> None:
        # dict-frame 경로에서도 동일 규칙이 적용되어야 한다.
        events_no_face = self.detector.detect(
            {"gesture": "fist", "gesture_confidence": 1.0, "wrist_y": 0.1},
            now=self.now,
            face_center=None,
        )
        self.assertEqual(events_no_face, [])

        events_below_face = self.detector.detect(
            {"gesture": "fist", "gesture_confidence": 1.0, "wrist_y": 0.8},
            now=self.now,
            face_center=(0.5, 0.5),
        )
        self.assertEqual(events_below_face, [])

        events_above_face = self.detector.detect(
            {"gesture": "fist", "gesture_confidence": 1.0, "wrist_y": 0.2},
            now=self.now,
            face_center=(0.5, 0.5),
        )
        self.assertEqual(len(events_above_face), 1)
        self.assertEqual(events_above_face[0].payload["gesture"], "fist")


if __name__ == "__main__":
    unittest.main()
