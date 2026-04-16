"""T-013: 타이머 스케줄러.

타이머 등록/해제, timer.expired 이벤트 발행.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)


@dataclass
class TimerEntry:
    timer_id: str
    label: str
    expire_at: float
    created_at: float = field(default_factory=time.time)


class TimerScheduler:
    """메인 프로세스 내부 타이머 스케줄러."""

    def __init__(self) -> None:
        self._timers: Dict[str, TimerEntry] = {}

    def create_timer(self, duration_ms: float, label: str = "") -> str:
        """타이머 등록. timer_id 반환."""
        timer_id = uuid.uuid4().hex[:8]
        expire_at = time.time() + duration_ms / 1000
        self._timers[timer_id] = TimerEntry(
            timer_id=timer_id,
            label=label,
            expire_at=expire_at,
        )
        logger.info("Timer created: %s (%s) expires in %dms", timer_id, label, duration_ms)
        return timer_id

    def cancel_timer(self, timer_id: str) -> bool:
        """타이머 해제."""
        if timer_id in self._timers:
            del self._timers[timer_id]
            return True
        return False

    def tick(self) -> List[Event]:
        """만료된 타이머에 대해 timer.expired 이벤트 목록 반환."""
        now = time.time()
        expired: List[Event] = []
        expired_ids: List[str] = []

        for tid, entry in self._timers.items():
            if now >= entry.expire_at:
                expired_ids.append(tid)
                expired.append(
                    Event(
                        topic=Topics.TIMER_EXPIRED,
                        source="main/scheduler",
                        payload={"timer_id": tid, "label": entry.label},
                        timestamp=now,
                    )
                )

        for tid in expired_ids:
            del self._timers[tid]

        return expired

    @property
    def active_count(self) -> int:
        return len(self._timers)

    def list_timers(self) -> List[Dict]:
        return [
            {"timer_id": e.timer_id, "label": e.label, "expire_at": e.expire_at}
            for e in self._timers.values()
        ]
