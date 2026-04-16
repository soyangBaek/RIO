"""T-018: System HUD layer.

Layer 3 – 시스템 상태 표시: 타이머, 날씨, degraded 상태 등.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HudItem:
    """HUD 에 표시할 하나의 요소."""
    item_id: str
    icon: str = ""
    text: str = ""
    position: str = "top-right"  # top-left, top-right, bottom-left, bottom-right
    timeout_at: Optional[float] = None  # 자동 제거 시각

    @property
    def is_expired(self) -> bool:
        if self.timeout_at is None:
            return False
        return time.time() >= self.timeout_at


class HudManager:
    """System HUD 요소 관리."""

    def __init__(self) -> None:
        self._items: Dict[str, HudItem] = {}

    def show(
        self,
        item_id: str,
        text: str,
        icon: str = "",
        position: str = "top-right",
        duration_ms: Optional[float] = None,
    ) -> None:
        timeout = None
        if duration_ms is not None:
            timeout = time.time() + duration_ms / 1000
        self._items[item_id] = HudItem(
            item_id=item_id,
            icon=icon,
            text=text,
            position=position,
            timeout_at=timeout,
        )

    def hide(self, item_id: str) -> None:
        self._items.pop(item_id, None)

    def tick(self) -> None:
        """만료된 HUD 아이템 제거."""
        expired = [k for k, v in self._items.items() if v.is_expired]
        for k in expired:
            del self._items[k]

    def get_visible_items(self) -> List[Dict[str, Any]]:
        self.tick()
        return [
            {"id": i.item_id, "icon": i.icon, "text": i.text, "position": i.position}
            for i in self._items.values()
        ]

    def show_error(self, text: str, duration_ms: float = 3000) -> None:
        self.show("error", text, icon="⚠", duration_ms=duration_ms)

    def show_timer(self, timer_id: str, label: str) -> None:
        self.show(f"timer_{timer_id}", label, icon="⏱", position="top-left")

    def hide_timer(self, timer_id: str) -> None:
        self.hide(f"timer_{timer_id}")
