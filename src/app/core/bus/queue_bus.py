"""T-003: multiprocessing.Queue 기반 이벤트 버스.

워커 프로세스 → 메인 오케스트레이터 단방향 이벤트 전달.
publish/subscribe 인터페이스 제공.
overflow 시 drop_oldest 정책.
"""
from __future__ import annotations

import logging
from multiprocessing import Queue
from queue import Empty, Full
from typing import Optional

from src.app.core.events.models import Event

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIZE = 256


class QueueBus:
    """bounded multiprocessing.Queue 래퍼.

    - publish(): 이벤트를 큐에 넣는다. overflow 시 가장 오래된 이벤트를 drop.
    - poll(): 이벤트를 꺼낸다. 없으면 None.
    """

    def __init__(self, maxsize: int = DEFAULT_MAX_SIZE) -> None:
        self._queue: Queue = Queue(maxsize=maxsize)
        self._maxsize = maxsize

    # ── publish ──────────────────────────────────────────────
    def publish(self, event: Event) -> None:
        """이벤트를 큐에 넣는다. 꽉 차면 drop_oldest."""
        try:
            self._queue.put_nowait(event)
        except Full:
            # drop oldest
            try:
                dropped = self._queue.get_nowait()
                logger.warning("QueueBus overflow – dropped %s", dropped.topic)
            except Empty:
                pass
            try:
                self._queue.put_nowait(event)
            except Full:
                logger.error("QueueBus still full after drop – event lost: %s", event.topic)

    # ── poll ─────────────────────────────────────────────────
    def poll(self, timeout: float = 0.0) -> Optional[Event]:
        """이벤트 1개를 꺼낸다. 없으면 None."""
        try:
            if timeout > 0:
                return self._queue.get(timeout=timeout)
            return self._queue.get_nowait()
        except Empty:
            return None

    # ── drain ────────────────────────────────────────────────
    def drain(self, max_events: int = 64) -> list[Event]:
        """큐에서 최대 max_events 개 이벤트를 한 번에 꺼낸다."""
        events: list[Event] = []
        for _ in range(max_events):
            ev = self.poll()
            if ev is None:
                break
            events.append(ev)
        return events

    @property
    def qsize_approx(self) -> int:
        return self._queue.qsize()
