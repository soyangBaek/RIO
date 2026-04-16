"""T-017: Eye tracking – 얼굴 중심 좌표 기반 눈동자/시선 애니메이션.

architecture.md §6.4 좌표 규격 참조.
normalized frame coordinates [0.0..1.0] → 화면 눈동자 위치.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class EyePosition:
    """눈동자 목표 위치 (normalized 0.0~1.0)."""
    x: float = 0.5  # 중앙
    y: float = 0.5
    timestamp: float = 0.0


class EyeTracker:
    """face center → eye position 변환기.

    카메라 좌표(normalized)를 화면 눈동자 위치로 매핑.
    부드러운 추적을 위한 lerp 적용.
    """

    def __init__(self, smoothing: float = 0.15) -> None:
        self._smoothing = smoothing
        self._current = EyePosition()
        self._target = EyePosition()
        self._last_update = time.time()
        self._face_visible = False

    def update_face_center(self, center_x: float, center_y: float) -> None:
        """vision.face.moved 이벤트의 center 좌표 수신."""
        self._target.x = center_x
        self._target.y = center_y
        self._target.timestamp = time.time()
        self._face_visible = True

    def on_face_lost(self) -> None:
        """얼굴 사라짐 → 눈 중앙 복귀."""
        self._target.x = 0.5
        self._target.y = 0.5
        self._face_visible = False

    def tick(self) -> EyePosition:
        """매 프레임 호출. lerp 적용된 현재 눈 위치 반환."""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        # lerp factor (smoothing)
        t = min(1.0, self._smoothing * dt * 60)  # 60fps 기준
        self._current.x += (self._target.x - self._current.x) * t
        self._current.y += (self._target.y - self._current.y) * t
        self._current.timestamp = now

        return self._current

    @property
    def is_tracking(self) -> bool:
        return self._face_visible

    def get_position(self) -> Tuple[float, float]:
        return (self._current.x, self._current.y)
