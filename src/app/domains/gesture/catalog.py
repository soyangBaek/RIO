"""T-052: 제스처 카탈로그 – 인식 가능한 제스처 정의.

손총, V자, 손 흔들기, 고개 방향 등.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class GestureEntry:
    """제스처 정의."""
    name: str
    description: str
    action: str  # 매핑될 intent 또는 반응
    source: str = "vision"  # vision or touch


# 카탈로그
GESTURE_CATALOG: Dict[str, GestureEntry] = {
    "v_sign": GestureEntry(
        name="v_sign",
        description="V자 (피스)",
        action="camera.capture",
    ),
    "open_palm": GestureEntry(
        name="open_palm",
        description="손 흔들기",
        action="greeting",
    ),
    "thumbs_up": GestureEntry(
        name="thumbs_up",
        description="엄지 척",
        action="system.ack",
    ),
    "wave": GestureEntry(
        name="wave",
        description="바이바이",
        action="farewell",
    ),
}


class GestureCatalog:
    """제스처 카탈로그 조회."""

    def __init__(self) -> None:
        self._catalog = dict(GESTURE_CATALOG)

    def get(self, gesture_name: str) -> GestureEntry | None:
        return self._catalog.get(gesture_name)

    def all_gestures(self) -> List[GestureEntry]:
        return list(self._catalog.values())

    def action_for(self, gesture_name: str) -> str | None:
        entry = self._catalog.get(gesture_name)
        return entry.action if entry else None
