"""T-021: 터치 제스처 매퍼.

탭/드래그/쓰다듬기를 분류하고 의미를 부여.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class GestureType:
    TAP = "tap"
    STROKE = "stroke"
    PETTING = "petting"       # 느린 드래그
    SWIPE = "swipe"           # 빠른 드래그
    LONG_PRESS = "long_press"


class GestureMapper:
    """터치 이벤트를 제스처로 분류."""

    def __init__(self) -> None:
        self._petting_min_duration = 0.3
        self._petting_min_points = 5
        self._swipe_max_duration = 0.3

    def classify_tap(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """tap 이벤트 분류 – 항상 탭."""
        return {
            "gesture": GestureType.TAP,
            "x": payload.get("x", 0),
            "y": payload.get("y", 0),
        }

    def classify_stroke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """stroke 이벤트를 petting/swipe 로 분류."""
        duration = payload.get("duration", 0)
        path = payload.get("path", [])

        if duration >= self._petting_min_duration and len(path) >= self._petting_min_points:
            return {
                "gesture": GestureType.PETTING,
                "duration": duration,
                "path_length": len(path),
            }

        if duration <= self._swipe_max_duration and len(path) >= 2:
            dx = path[-1].get("x", 0) - path[0].get("x", 0)
            dy = path[-1].get("y", 0) - path[0].get("y", 0)
            direction = "right" if dx > 0 else "left"
            if abs(dy) > abs(dx):
                direction = "down" if dy > 0 else "up"
            return {
                "gesture": GestureType.SWIPE,
                "direction": direction,
                "duration": duration,
            }

        return {
            "gesture": GestureType.STROKE,
            "duration": duration,
            "path_length": len(path),
        }
