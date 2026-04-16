"""T-004: 이벤트 라우터 – 구독/발행 + 메인 루프 연결.

메인 프로세스 내부에서 topic 기반 구독/발행을 처리.
워커 큐(QueueBus)에서 이벤트를 drain 하여 내부 subscribers 에 전달.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set

from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event

logger = logging.getLogger(__name__)

Subscriber = Callable[[Event], None]


class EventRouter:
    """메인 프로세스 내부 이벤트 라우터.

    - subscribe(topic_or_prefix, callback)
    - publish(event)  -> 내부 subscribers 즉시 호출
    - ingest(bus)     -> QueueBus 에서 drain 후 내부 발행
    """

    def __init__(self) -> None:
        # exact topic -> [callbacks]
        self._exact: Dict[str, List[Subscriber]] = defaultdict(list)
        # prefix -> [callbacks]  (e.g. "voice.*" → prefix "voice.")
        self._prefix: Dict[str, List[Subscriber]] = defaultdict(list)
        # wildcard subscribers ("*")
        self._wildcard: List[Subscriber] = []

    # ── subscribe ────────────────────────────────────────────
    def subscribe(self, topic_pattern: str, callback: Subscriber) -> None:
        """topic_pattern 에 매칭되는 이벤트를 callback 으로 전달.

        - '*'           : 모든 이벤트
        - 'voice.*'     : voice. 로 시작하는 모든 토픽
        - 'timer.expired': 정확히 일치
        """
        if topic_pattern == "*":
            self._wildcard.append(callback)
        elif topic_pattern.endswith(".*"):
            prefix = topic_pattern[:-1]  # "voice.*" → "voice."
            self._prefix[prefix].append(callback)
        else:
            self._exact[topic_pattern].append(callback)

    # ── publish (내부) ───────────────────────────────────────
    def publish(self, event: Event) -> None:
        """내부 구독자에게 이벤트를 동기적으로 전달."""
        for cb in self._wildcard:
            _safe_call(cb, event)
        for cb in self._exact.get(event.topic, []):
            _safe_call(cb, event)
        for prefix, cbs in self._prefix.items():
            if event.topic.startswith(prefix):
                for cb in cbs:
                    _safe_call(cb, event)

    # ── ingest from worker bus ───────────────────────────────
    def ingest(self, bus: QueueBus, max_events: int = 64) -> List[Event]:
        """워커 큐에서 이벤트를 drain 하고 내부 발행. 처리된 이벤트 목록 반환."""
        events = bus.drain(max_events)
        for ev in events:
            self.publish(ev)
        return events


def _safe_call(cb: Subscriber, event: Event) -> None:
    try:
        cb(event)
    except Exception:
        logger.exception("Subscriber error on topic=%s", event.topic)
