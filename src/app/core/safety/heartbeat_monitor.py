"""T-014: 워커 생존 감시 – heartbeat monitor.

워커 프로세스가 주기적으로 heartbeat 를 보내고,
메인에서 일정 시간 수신 못하면 degraded 모드.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_TIMEOUT_MS = 5000


class HeartbeatMonitor:
    """워커 heartbeat 수신 및 timeout 감지."""

    def __init__(self, timeout_ms: float = DEFAULT_HEARTBEAT_TIMEOUT_MS) -> None:
        self._timeout_ms = timeout_ms
        self._last_seen: Dict[str, float] = {}

    def record_heartbeat(self, worker_name: str, timestamp: Optional[float] = None) -> None:
        self._last_seen[worker_name] = timestamp or time.time()

    def handle_event(self, event: Event) -> None:
        """system.worker.heartbeat 이벤트 처리."""
        if event.topic == Topics.SYSTEM_WORKER_HEARTBEAT:
            worker = event.payload.get("worker", "unknown")
            self.record_heartbeat(worker, event.timestamp)

    def check_timeouts(self) -> List[Event]:
        """timeout 된 워커에 대해 degraded 이벤트 목록 반환."""
        now = time.time()
        events: List[Event] = []
        for worker, last_ts in list(self._last_seen.items()):
            elapsed_ms = (now - last_ts) * 1000
            if elapsed_ms > self._timeout_ms:
                logger.warning("Worker %s heartbeat timeout (%.0fms)", worker, elapsed_ms)
                cap = "mic_available" if worker == "audio_worker" else "camera_available"
                events.append(
                    Event(
                        topic=Topics.SYSTEM_DEGRADED_ENTERED,
                        source="main/safety",
                        payload={"reason": f"{worker} heartbeat timeout", "lost_capability": cap},
                        timestamp=now,
                    )
                )
                # timeout 기록 리셋 (반복 경고 방지)
                self._last_seen[worker] = now
        return events

    def register_worker(self, worker_name: str) -> None:
        """워커를 등록하고 현재 시각으로 초기화."""
        self._last_seen[worker_name] = time.time()
