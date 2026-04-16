"""T-020: 터치스크린 입력 어댑터.

터치 이벤트를 표준 이벤트로 변환. pygame 이벤트 루프와 통합.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)


class TouchInput:
    """터치스크린 raw 입력 수집.

    pygame 또는 evdev 기반. headless 모드 지원.
    """

    def __init__(self, screen_width: int = 480, screen_height: int = 320, headless: bool = False) -> None:
        self._width = screen_width
        self._height = screen_height
        self._headless = headless
        self._touch_points: List[Dict[str, Any]] = []
        self._touch_start: Optional[Dict[str, Any]] = None
        self._stroke_path: List[Dict[str, float]] = []

    def poll_events(self) -> List[Event]:
        """현재 발생한 터치 이벤트 목록을 반환."""
        if self._headless:
            return []

        events: List[Event] = []
        try:
            import pygame
            for pg_event in pygame.event.get(eventtype=[
                pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION
            ]):
                ev = self._handle_pygame_event(pg_event)
                if ev:
                    events.append(ev)
        except ImportError:
            pass
        return events

    def _handle_pygame_event(self, pg_event: Any) -> Optional[Event]:
        import pygame
        now = time.time()

        if pg_event.type == pygame.MOUSEBUTTONDOWN:
            x, y = pg_event.pos
            self._touch_start = {"x": x, "y": y, "time": now}
            self._stroke_path = [{"x": x / self._width, "y": y / self._height}]
            return None

        elif pg_event.type == pygame.MOUSEMOTION:
            if self._touch_start:
                x, y = pg_event.pos
                self._stroke_path.append({"x": x / self._width, "y": y / self._height})
            return None

        elif pg_event.type == pygame.MOUSEBUTTONUP:
            x, y = pg_event.pos
            if self._touch_start is None:
                return None

            duration = now - self._touch_start["time"]
            dx = x - self._touch_start["x"]
            dy = y - self._touch_start["y"]
            distance = (dx ** 2 + dy ** 2) ** 0.5

            self._touch_start = None

            if distance < 10 and duration < 0.3:
                # Tap
                return Event(
                    topic=Topics.TOUCH_TAP_DETECTED,
                    source="main/touch",
                    payload={"x": x / self._width, "y": y / self._height},
                    timestamp=now,
                )
            else:
                # Stroke
                path = list(self._stroke_path)
                self._stroke_path = []
                return Event(
                    topic=Topics.TOUCH_STROKE_DETECTED,
                    source="main/touch",
                    payload={"path": path, "duration": duration},
                    timestamp=now,
                )

        return None

    def inject_tap(self, x: float, y: float) -> Event:
        """테스트용 tap 이벤트 생성."""
        return Event(
            topic=Topics.TOUCH_TAP_DETECTED,
            source="main/touch",
            payload={"x": x, "y": y},
            timestamp=time.time(),
        )

    def inject_stroke(self, path: List[Dict[str, float]], duration: float = 0.5) -> Event:
        """테스트용 stroke 이벤트 생성."""
        return Event(
            topic=Topics.TOUCH_STROKE_DETECTED,
            source="main/touch",
            payload={"path": path, "duration": duration},
            timestamp=time.time(),
        )
