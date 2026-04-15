from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


Payload = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Event:
    """Canonical event envelope shared by workers and the main loop."""

    topic: str
    source: str
    timestamp: datetime
    payload: Payload = field(default_factory=dict)
    confidence: float | None = None
    trace_id: str | None = None

    @classmethod
    def create(
        cls,
        topic: str,
        source: str,
        payload: Mapping[str, Any] | None = None,
        *,
        confidence: float | None = None,
        trace_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> "Event":
        return cls(
            topic=topic,
            source=source,
            timestamp=timestamp or datetime.now(timezone.utc),
            payload=dict(payload or {}),
            confidence=confidence,
            trace_id=trace_id or uuid4().hex,
        )

    def with_payload(self, **updates: Any) -> "Event":
        merged = dict(self.payload)
        merged.update(updates)
        return Event.create(
            topic=self.topic,
            source=self.source,
            payload=merged,
            confidence=self.confidence,
            trace_id=self.trace_id,
            timestamp=self.timestamp,
        )

