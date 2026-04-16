"""T-015: Capability 관리.

센서 실패 시 부분 기능 유지를 위한 capability flag 관리.
architecture.md §8.2 기준.
"""
from __future__ import annotations

import logging
from typing import List

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.store import Capabilities, Store

logger = logging.getLogger(__name__)


class CapabilityManager:
    """capability flag 관리 + degraded 이벤트 처리."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def handle_degraded(self, event: Event) -> None:
        """system.degraded.entered 이벤트 처리."""
        if event.topic != Topics.SYSTEM_DEGRADED_ENTERED:
            return
        lost = event.payload.get("lost_capability", "")
        if lost == "camera_available":
            self._store.capabilities.camera_available = False
            logger.warning("Camera capability lost")
        elif lost == "mic_available":
            self._store.capabilities.mic_available = False
            logger.warning("Mic capability lost")
        elif lost == "touch_available":
            self._store.capabilities.touch_available = False
            logger.warning("Touch capability lost")

    def restore(self, capability: str) -> None:
        """기능 복구."""
        if hasattr(self._store.capabilities, capability):
            setattr(self._store.capabilities, capability, True)
            logger.info("Capability restored: %s", capability)

    @property
    def degraded_capabilities(self) -> List[str]:
        """비활성 capability 목록."""
        caps = self._store.capabilities
        result = []
        if not caps.camera_available:
            result.append("camera_available")
        if not caps.mic_available:
            result.append("mic_available")
        if not caps.touch_available:
            result.append("touch_available")
        return result

    @property
    def is_fully_operational(self) -> bool:
        return len(self.degraded_capabilities) == 0
