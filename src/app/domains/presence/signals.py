"""T-024: Presence signals – 사용자 증거 집계.

presence 도메인의 핵심 신호 판단.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.store import Store


class PresenceSignals:
    """사용자 존재 신호 집계."""

    def __init__(self, store: Store, config: Dict[str, Any]) -> None:
        self._store = store
        self._config = config.get("presence", {})

    def is_user_evidence(self, event: Event) -> bool:
        """이벤트가 사용자 존재 증거인지."""
        return event.topic in Topics.USER_EVIDENCE_TOPICS

    def is_interaction(self, event: Event) -> bool:
        """이벤트가 상호작용 증거인지."""
        return event.topic in Topics.INTERACTION_TOPICS

    def confirmed_user_and_interacting(self) -> bool:
        """face_present AND 최근 상호작용 있음."""
        if not self._store.face_present:
            return False
        if self._store.last_interaction_at is None:
            return False
        cooldown = self._config.get("face_lost_timeout_ms", 800) / 1000
        return (time.time() - self._store.last_interaction_at) < cooldown * 5

    @property
    def face_present(self) -> bool:
        return self._store.face_present

    @property
    def time_since_last_face(self) -> float:
        """마지막 얼굴 감지 이후 경과 시간 (초). 없으면 inf."""
        if self._store.last_face_seen_at is None:
            return float("inf")
        return time.time() - self._store.last_face_seen_at

    @property
    def time_since_last_interaction(self) -> float:
        if self._store.last_interaction_at is None:
            return float("inf")
        return time.time() - self._store.last_interaction_at
