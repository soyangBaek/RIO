"""Intent duplicate filter.

STT engines occasionally emit the same transcript twice in quick succession
— or the user repeats themselves inside the ``intent_cooldown_ms`` window.
This filter drops the later hit so a single utterance does not trigger the
downstream pipeline twice. Keyed per intent id so independent commands are
not starved.
"""
from __future__ import annotations

from typing import Dict, Optional


class IntentDedupe:
    def __init__(self, cooldown_ms: int = 1_500) -> None:
        if cooldown_ms <= 0:
            raise ValueError("cooldown_ms must be positive")
        self._cooldown_s = cooldown_ms / 1000.0
        self._last_seen: Dict[str, float] = {}

    def should_accept(self, intent_id: str, now: float) -> bool:
        """Return ``True`` if ``intent_id`` may pass; record it on accept."""
        last = self._last_seen.get(intent_id)
        if last is not None and (now - last) < self._cooldown_s:
            return False
        self._last_seen[intent_id] = now
        return True

    def clear(self, intent_id: Optional[str] = None) -> None:
        if intent_id is None:
            self._last_seen.clear()
        else:
            self._last_seen.pop(intent_id, None)
