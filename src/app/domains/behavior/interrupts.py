"""T-029: Activity 인터럽트 정책.

state-machine.md §4.1 기준.
Alerting, photo, deferred_intent 규칙.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.models import ActivityState, ExecutingKind
from src.app.core.state.store import Store

logger = logging.getLogger(__name__)

# MVP high_priority_alert = timer.expired 만
HIGH_PRIORITY_ALERTS = frozenset({Topics.TIMER_EXPIRED})

# photo 중 허용되는 topic
PHOTO_ALLOWED = frozenset({
    "system.cancel", "system.ack",
})

# game/dance 중 허용되는 topic
GAME_DANCE_ALLOWED = frozenset({
    "system.cancel",
})


class InterruptPolicy:
    """Activity 인터럽트 정책."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def should_block_event(self, event: Event) -> bool:
        """이벤트가 현재 Activity 에 의해 차단되어야 하는지.

        Returns True → 이벤트를 무시 또는 defer.
        """
        activity = self._store.activity_state
        kind = self._store.active_executing_kind

        if activity != ActivityState.EXECUTING:
            return False

        # Executing(photo): 새 intent 무시, timer.expired defer
        if kind == ExecutingKind.PHOTO:
            if event.topic == Topics.VOICE_INTENT_DETECTED:
                intent = event.payload.get("intent", "")
                if intent not in PHOTO_ALLOWED:
                    logger.debug("Photo mode: blocking intent %s", intent)
                    return True
            if event.topic == Topics.TIMER_EXPIRED:
                # defer alerting
                logger.debug("Photo mode: deferring timer.expired")
                return True

        # Executing(game/dance): 새 intent 무시
        if kind in (ExecutingKind.GAME, ExecutingKind.DANCE):
            if event.topic == Topics.VOICE_INTENT_DETECTED:
                intent = event.payload.get("intent", "")
                if intent not in GAME_DANCE_ALLOWED:
                    logger.debug("Game/dance mode: blocking intent %s", intent)
                    return True

        return False

    def should_defer_intent(self, event: Event) -> bool:
        """intent를 deferred_intent로 저장해야 하는지."""
        if self._store.activity_state != ActivityState.EXECUTING:
            return False

        kind = self._store.active_executing_kind
        if kind in (ExecutingKind.SMARTHOME, ExecutingKind.WEATHER, ExecutingKind.TIMER_SETUP):
            if event.topic == Topics.VOICE_INTENT_DETECTED:
                return True

        return False

    def defer_intent(self, event: Event) -> None:
        """intent를 store.deferred_intent에 저장 (최신 1개만)."""
        self._store.deferred_intent = event.payload.copy()
        logger.debug("Deferred intent: %s", event.payload.get("intent"))

    def apply(self, event: Event) -> Optional[Event]:
        """인터럽트 정책 적용. 차단되면 None 반환, 통과하면 event 반환."""
        if self.should_defer_intent(event):
            self.defer_intent(event)
            return None

        if self.should_block_event(event):
            return None

        return event
