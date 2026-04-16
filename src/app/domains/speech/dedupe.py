"""T-028: Intent dedupe – 동일 intent 재수신 무시.

behavior.intent_cooldown_ms 이내의 중복 intent 는 무시.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


class IntentDedupe:
    """intent 중복 제거."""

    def __init__(self, cooldown_ms: float = 1500) -> None:
        self._cooldown_ms = cooldown_ms
        self._last_intents: Dict[str, float] = {}

    def is_duplicate(self, intent: str) -> bool:
        """intent 가 쿨다운 이내의 중복인지."""
        now = time.time()
        last = self._last_intents.get(intent)
        if last is not None and (now - last) * 1000 < self._cooldown_ms:
            return True
        self._last_intents[intent] = now
        return False

    def record(self, intent: str) -> None:
        """intent 기록 (is_duplicate와 별도로 수동 기록)."""
        self._last_intents[intent] = time.time()

    def clear(self) -> None:
        self._last_intents.clear()
