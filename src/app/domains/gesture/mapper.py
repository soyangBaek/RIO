"""T-053: 제스처 → 액션 매퍼.

vision.gesture.detected 이벤트의 gesture 이름을 intent/반응으로 변환.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.domains.gesture.catalog import GestureCatalog

logger = logging.getLogger(__name__)


class GestureActionMapper:
    """제스처 → 액션 매핑."""

    def __init__(self) -> None:
        self._catalog = GestureCatalog()

    def map_event(self, event: Event) -> Optional[Event]:
        """vision.gesture.detected → intent 이벤트로 변환.

        매핑 가능한 gesture면 voice.intent.detected 이벤트 반환.
        없으면 None.
        """
        if event.topic != Topics.VISION_GESTURE_DETECTED:
            return None

        gesture_name = event.payload.get("gesture", "")
        action = self._catalog.action_for(gesture_name)

        if not action:
            logger.debug("No action mapped for gesture: %s", gesture_name)
            return None

        # 실제 intent로 매핑 가능한 것만 이벤트 생성
        if action.startswith("camera.") or action.startswith("system.") or action.startswith("smarthome."):
            return Event(
                topic=Topics.VOICE_INTENT_DETECTED,
                source="main/gesture",
                payload={
                    "intent": action,
                    "text": f"[gesture:{gesture_name}]",
                    "confidence": event.payload.get("confidence", 0.8),
                },
                timestamp=event.timestamp,
            )

        # non-intent 반응 (greeting, farewell 등)은 로깅만
        logger.info("Gesture reaction: %s → %s", gesture_name, action)
        return None
