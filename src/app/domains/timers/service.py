"""T-033: Timer service – 타이머 생성/관리.

voice intent → timer_scheduler 등록 → 완료 알림.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from src.app.core.scheduler.timer_scheduler import TimerScheduler
from src.app.domains.speech.timer_parser import TimerParser

logger = logging.getLogger(__name__)


class TimerService:
    """타이머 도메인 서비스."""

    def __init__(self, scheduler: TimerScheduler) -> None:
        self._scheduler = scheduler
        self._parser = TimerParser()

    def handle(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        """executor_registry 핸들러.

        payload['text'] 에서 시간 파싱 → 타이머 등록.
        """
        try:
            text = payload.get("text", "")
            duration_ms, label = self._parser.parse(text)

            if duration_ms is None or duration_ms <= 0:
                done_callback(False, error="Could not parse timer duration")
                return

            timer_id = self._scheduler.create_timer(duration_ms, label=label)
            formatted = self._parser.format_duration(duration_ms)
            logger.info("Timer set: %s (%s)", formatted, timer_id)

            done_callback(True, result={
                "timer_id": timer_id,
                "duration_ms": duration_ms,
                "label": label,
                "formatted": formatted,
            })

        except Exception as e:
            logger.exception("Timer service error")
            done_callback(False, error=str(e))
