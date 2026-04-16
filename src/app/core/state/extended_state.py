"""T-007: Extended state 업데이트.

이벤트를 받아 face_present, last_face_seen_at, deferred_intent 등 갱신.
state-machine.md §3.1 기준.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.store import Store


def update_extended_state(store: Store, event: Event, config: Dict[str, Any]) -> None:
    """이벤트를 기반으로 extended state 필드를 갱신한다."""
    now = event.timestamp or time.time()
    topic = event.topic

    # ── face_present / last_face_seen_at ─────────────────────
    if topic == Topics.VISION_FACE_DETECTED:
        store.face_present = True
        store.last_face_seen_at = now

    elif topic == Topics.VISION_FACE_LOST:
        store.face_present = False

    # ── user_evidence ────────────────────────────────────────
    if topic in Topics.USER_EVIDENCE_TOPICS:
        store.last_user_evidence_at = now

    # ── interaction ──────────────────────────────────────────
    if topic in Topics.INTERACTION_TOPICS:
        store.last_interaction_at = now

    # ── away_started_at (Context Away 진입 시 기록) ──────────
    # 실제 전이 시 reducers 에서도 갱신하지만, face_lost 시점 기록
    if topic == Topics.VISION_FACE_LOST and store.last_face_seen_at:
        # away_started_at 은 Away 전이 시 갱신 (여기서는 후보값 유지)
        pass

    # ── deferred_intent 관련은 activity_fsm / interrupts 에서 처리 ─

    # ── face.moved (eye tracking용, extended state에 영향 없음) ─


# ── 파생 상황 계산 ──────────────────────────────────────────
def is_searching_for_user(store: Store) -> bool:
    """Activity==Listening AND face_present==False."""
    from src.app.core.state.models import ActivityState
    return (
        store.activity_state == ActivityState.LISTENING
        and not store.face_present
    )


def recent_face_loss(store: Store, config: Dict[str, Any]) -> bool:
    """face_present==False AND now - last_face_seen_at < face_lost_timeout_ms."""
    if store.face_present or store.last_face_seen_at is None:
        return False
    timeout_ms = config.get("presence", {}).get("face_lost_timeout_ms", 800)
    return (time.time() - store.last_face_seen_at) * 1000 < timeout_ms


def just_reappeared(store: Store, prev_context: str, config: Dict[str, Any]) -> bool:
    """직전 Context가 Away/Sleepy → 현재 Idle, away 경과가 welcome_min_away_ms 이상."""
    from src.app.core.state.models import ContextState
    if store.context_state != ContextState.IDLE:
        return False
    if prev_context not in (ContextState.AWAY.value, ContextState.SLEEPY.value):
        return False
    if store.away_started_at is None:
        return False
    min_away_ms = config.get("presence", {}).get("welcome_min_away_ms", 3000)
    return (time.time() - store.away_started_at) * 1000 >= min_away_ms
