"""T-025: Presence helpers – 파생 상황 판단.

just_reappeared, recent_face_loss, is_searching_for_user 등.
extended_state.py의 함수를 래핑하여 도메인 레벨 API 제공.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from src.app.core.state.extended_state import (
    is_searching_for_user as _is_searching,
    just_reappeared as _just_reappeared,
    recent_face_loss as _recent_face_loss,
)
from src.app.core.state.models import ContextState
from src.app.core.state.store import Store


class PresenceHelpers:
    """Presence 파생 상황 helper."""

    def __init__(self, store: Store, config: Dict[str, Any]) -> None:
        self._store = store
        self._config = config

    def is_searching_for_user(self) -> bool:
        return _is_searching(self._store)

    def recent_face_loss(self) -> bool:
        return _recent_face_loss(self._store, self._config)

    def just_reappeared(self, prev_context_value: str) -> bool:
        return _just_reappeared(self._store, prev_context_value, self._config)

    @property
    def away_duration_ms(self) -> float:
        """현재 Away 상태 경과 시간 (ms)."""
        if self._store.away_started_at is None:
            return 0
        return (time.time() - self._store.away_started_at) * 1000
