"""T-001: 공통 이벤트 envelope dataclass.

architecture.md §3, §6.1 기준.
모든 워커/메인이 공유하는 이벤트 포맷.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Event:
    """RIO 표준 이벤트 envelope.

    필수: topic, source, timestamp, payload
    권장: confidence, trace_id
    """

    topic: str
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    confidence: Optional[float] = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # ── helpers ──────────────────────────────────────────────
    @property
    def domain(self) -> str:
        """topic 첫 세그먼트 (e.g. 'voice')."""
        return self.topic.split(".")[0]

    def with_payload(self, **extra: Any) -> "Event":
        """payload 필드를 추가한 새 Event 반환 (immutable)."""
        merged = {**self.payload, **extra}
        return Event(
            topic=self.topic,
            source=self.source,
            payload=merged,
            timestamp=self.timestamp,
            confidence=self.confidence,
            trace_id=self.trace_id,
        )
