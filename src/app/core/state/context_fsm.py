"""T-008: Context FSM – 전이 규칙.

state-machine.md §3 기준.
Away/Idle/Engaged/Sleepy 전이만 담당. 표정/UI는 scene_selector에서 파생.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.models import ContextState
from src.app.core.state.store import Store


def context_transition(
    store: Store,
    event: Event,
    config: Dict[str, Any],
) -> Optional[Tuple[ContextState, ContextState]]:
    """이벤트와 현재 store 를 보고 Context 전이를 반환.

    전이가 없으면 None, 있으면 (from_state, to_state).
    """
    now = event.timestamp or time.time()
    current = store.context_state
    topic = event.topic
    presence_cfg = config.get("presence", {})
    behavior_cfg = config.get("behavior", {})

    # ── Away → Idle : user_evidence_detected ─────────────────
    if current == ContextState.AWAY:
        if topic in Topics.USER_EVIDENCE_TOPICS:
            return (ContextState.AWAY, ContextState.IDLE)

    # ── Idle ─────────────────────────────────────────────────
    elif current == ContextState.IDLE:
        # → Engaged : confirmed_user_and_interacting
        if topic in Topics.INTERACTION_TOPICS and store.face_present:
            return (ContextState.IDLE, ContextState.ENGAGED)

        # → Away : no_face_long_timeout
        if _no_face_long_timeout(store, now, presence_cfg):
            return (ContextState.IDLE, ContextState.AWAY)

        # → Sleepy : long_idle
        if _long_idle(store, now, behavior_cfg):
            return (ContextState.IDLE, ContextState.SLEEPY)

    # ── Engaged ──────────────────────────────────────────────
    elif current == ContextState.ENGAGED:
        # → Idle : no_interaction_for_a_while
        if _no_interaction_for_a_while(store, now, behavior_cfg):
            return (ContextState.ENGAGED, ContextState.IDLE)

        # → Sleepy : long_idle
        if _long_idle(store, now, behavior_cfg):
            return (ContextState.ENGAGED, ContextState.SLEEPY)

    # ── Sleepy ───────────────────────────────────────────────
    elif current == ContextState.SLEEPY:
        # → Idle : gentle_wake (face_detected 만)
        if topic == Topics.VISION_FACE_DETECTED:
            return (ContextState.SLEEPY, ContextState.IDLE)

        # → Away : no_face_long_timeout
        if _no_face_long_timeout(store, now, presence_cfg):
            return (ContextState.SLEEPY, ContextState.AWAY)

    return None


# ── helper predicates ────────────────────────────────────────
def _no_face_long_timeout(store: Store, now: float, cfg: Dict) -> bool:
    away_ms = cfg.get("away_timeout_ms", 60_000)
    if store.last_face_seen_at is None and store.last_user_evidence_at is None:
        return False
    ref = store.last_face_seen_at or store.last_user_evidence_at or 0
    return (now - ref) * 1000 >= away_ms


def _long_idle(store: Store, now: float, cfg: Dict) -> bool:
    timeout_ms = cfg.get("idle_to_sleepy_timeout_ms", 120_000)
    ref = store.last_interaction_at or store.last_user_evidence_at
    if ref is None:
        return False
    return (now - ref) * 1000 >= timeout_ms


def _no_interaction_for_a_while(store: Store, now: float, cfg: Dict) -> bool:
    """Engaged → Idle 전이 조건. 상호작용이 일정 시간 이상 없음."""
    timeout_ms = cfg.get("idle_to_sleepy_timeout_ms", 120_000) // 4  # 1/4 기준
    ref = store.last_interaction_at
    if ref is None:
        return False
    return (now - ref) * 1000 >= timeout_ms
