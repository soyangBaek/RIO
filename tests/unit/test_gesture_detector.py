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


def _heart_hand(
    *,
    wrist_x: float,
    wrist_y: float = 0.5,
    thumb_tip: tuple[float, float],
    index_tip: tuple[float, float],
    index_pip: tuple[float, float] | None = None,
    fingers_curled: bool = True,
) -> list[_Landmark]:
    """하트 판정에 필요한 랜드마크를 배치한 손.

    fingers_curled=True 이면 중지/약지/소지를 모두 curl 상태(=extended 아님)로
    설정. False 이면 세 손가락을 extended 상태로 세팅해 curl 조건 실패를
    유도한다.
    """
    data = [_Landmark(wrist_x, wrist_y) for _ in range(21)]
    data[0] = _Landmark(wrist_x, wrist_y)              # wrist
    data[9] = _Landmark(wrist_x, wrist_y - 0.12)       # middle MCP — hand span 기준
    data[4] = _Landmark(thumb_tip[0], thumb_tip[1])
    data[8] = _Landmark(index_tip[0], index_tip[1])
    # 기본 index PIP: tip 보다 약간 위쪽(작은 y) — 하트 골짜기 조건 충족.
    if index_pip is None:
        index_pip = (index_tip[0], index_tip[1] - 0.05)
    data[6] = _Landmark(index_pip[0], index_pip[1])

    # 중지/약지/소지 — curl 여부에 따라 tip/pip/mcp 배치.
    # curled: tip.y >= pip.y >= mcp.y (은 False; _is_extended 가 False 가 되는 배치)
    # extended: tip.y < pip.y < mcp.y → _is_extended True
    fingers = ((9, 10, 12), (13, 14, 16), (17, 18, 20))
    for mcp_i, pip_i, tip_i in fingers:
        mcp_y = wrist_y - 0.10
        if fingers_curled:
            # tip 이 mcp 보다 아래 (손바닥 안쪽으로 말림) → _is_extended False
            data[mcp_i] = _Landmark(wrist_x, mcp_y)
            data[pip_i] = _Landmark(wrist_x, mcp_y + 0.03)
            data[tip_i] = _Landmark(wrist_x, mcp_y + 0.06)
        else:
            # tip 이 mcp 보다 위 (쭉 뻗음) → _is_extended True
            data[mcp_i] = _Landmark(wrist_x, mcp_y)
            data[pip_i] = _Landmark(wrist_x, mcp_y - 0.03)
            data[tip_i] = _Landmark(wrist_x, mcp_y - 0.06)
    return data


class GestureDetectorHeartTest(unittest.TestCase):
    @staticmethod
    def _detect(left: list[_Landmark], right: list[_Landmark]) -> dict | None:
        return GestureDetector._detect_heart(
            [_HandLandmarks(left).landmark, _HandLandmarks(right).landmark]
        )

    def test_heart_detected_when_all_conditions_met(self) -> None:
        left = _heart_hand(
            wrist_x=0.30,
            thumb_tip=(0.48, 0.52),   # 아래 중앙
            index_tip=(0.48, 0.40),   # 위 중앙 (PIP 보다 아래)
            index_pip=(0.42, 0.35),   # 손 바깥쪽, tip 보다 위
        )
        right = _heart_hand(
            wrist_x=0.70,
            thumb_tip=(0.52, 0.52),
            index_tip=(0.52, 0.40),
            index_pip=(0.58, 0.35),
        )
        metrics = self._detect(left, right)
        self.assertIsNotNone(metrics)
        self.assertTrue(metrics["thumbs_meet"])
        self.assertTrue(metrics["indices_meet"])
        self.assertTrue(metrics["heart_shape"])
        self.assertTrue(metrics["fingers_curled"])
        self.assertTrue(metrics["hands_apart"])
        self.assertTrue(metrics["symmetric"])
        self.assertTrue(metrics["top_valley"])

    def test_heart_rejected_when_thumbs_apart(self) -> None:
        left = _heart_hand(
            wrist_x=0.20,
            thumb_tip=(0.22, 0.52),
            index_tip=(0.40, 0.40),
        )
        right = _heart_hand(
            wrist_x=0.80,
            thumb_tip=(0.78, 0.52),
            index_tip=(0.60, 0.40),
        )
        self.assertIsNone(self._detect(left, right))

    def test_heart_rejected_when_thumbs_above_indices(self) -> None:
        left = _heart_hand(
            wrist_x=0.30,
            thumb_tip=(0.48, 0.40),   # 위
            index_tip=(0.48, 0.52),   # 아래
        )
        right = _heart_hand(
            wrist_x=0.70,
            thumb_tip=(0.52, 0.40),
            index_tip=(0.52, 0.52),
        )
        self.assertIsNone(self._detect(left, right))

    def test_heart_rejected_when_other_fingers_extended(self) -> None:
        # 양손 활짝 펼친 채 엄지+검지만 맞댄 모양. curl 조건 실패로 거절.
        left = _heart_hand(
            wrist_x=0.30,
            thumb_tip=(0.48, 0.52),
            index_tip=(0.48, 0.40),
            index_pip=(0.42, 0.35),
            fingers_curled=False,
        )
        right = _heart_hand(
            wrist_x=0.70,
            thumb_tip=(0.52, 0.52),
            index_tip=(0.52, 0.40),
            index_pip=(0.58, 0.35),
            fingers_curled=False,
        )
        metrics = self._detect(left, right)
        self.assertIsNone(metrics)

    def test_heart_rejected_when_hands_too_close(self) -> None:
        # 두 손 wrist 가 거의 같은 위치 → hands_apart 실패.
        left = _heart_hand(
            wrist_x=0.50,
            thumb_tip=(0.50, 0.52),
            index_tip=(0.50, 0.40),
            index_pip=(0.46, 0.35),
        )
        right = _heart_hand(
            wrist_x=0.51,
            thumb_tip=(0.51, 0.52),
            index_tip=(0.51, 0.40),
            index_pip=(0.54, 0.35),
        )
        self.assertIsNone(self._detect(left, right))

    def test_heart_rejected_when_no_top_valley(self) -> None:
        # 검지가 곧게 뻗어 PIP 가 tip 보다 위가 아님 → top_valley 실패.
        left = _heart_hand(
            wrist_x=0.30,
            thumb_tip=(0.48, 0.52),
            index_tip=(0.48, 0.40),
            index_pip=(0.48, 0.45),   # tip(0.40) 보다 아래(0.45) → 곧게 편 상태
        )
        right = _heart_hand(
            wrist_x=0.70,
            thumb_tip=(0.52, 0.52),
            index_tip=(0.52, 0.40),
            index_pip=(0.52, 0.45),
        )
        self.assertIsNone(self._detect(left, right))

    def test_heart_accepts_hands_regardless_of_input_order(self) -> None:
        # MediaPipe 가 오른손/왼손을 어느 순서로 주든 정렬 후 처리되어야 한다.
        left = _heart_hand(
            wrist_x=0.30,
            thumb_tip=(0.48, 0.52),
            index_tip=(0.48, 0.40),
            index_pip=(0.42, 0.35),
        )
        right = _heart_hand(
            wrist_x=0.70,
            thumb_tip=(0.52, 0.52),
            index_tip=(0.52, 0.40),
            index_pip=(0.58, 0.35),
        )
        self.assertIsNotNone(self._detect(left, right))
        self.assertIsNotNone(self._detect(right, left))


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
