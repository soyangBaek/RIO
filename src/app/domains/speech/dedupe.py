from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class IntentDeduper:
    cooldown_ms: int = 1500
    _last_seen: dict[str, datetime] = field(default_factory=dict)

    def accept(self, intent: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        previous = self._last_seen.get(intent)
        if previous is not None:
            delta_ms = (now - previous).total_seconds() * 1000.0
            if delta_ms < self.cooldown_ms:
                return False
        self._last_seen[intent] = now
        return True

    def cooldown_remaining_ms(self, intent: str, *, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        previous = self._last_seen.get(intent)
        if previous is None:
            return 0
        delta_ms = (now - previous).total_seconds() * 1000.0
        return max(int(self.cooldown_ms - delta_ms), 0)
