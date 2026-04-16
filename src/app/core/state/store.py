"""T-006: 전역 상태 저장소.

architecture.md §3.3 기준. authoritative + extended + runtime resources.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    OneshotName,
)


@dataclass
class ActiveOneshot:
    name: OneshotName
    priority: int
    started_at: float
    duration_ms: float

    @property
    def elapsed_ratio(self) -> float:
        elapsed = (time.time() - self.started_at) * 1000
        return min(elapsed / self.duration_ms, 1.0) if self.duration_ms > 0 else 1.0

    @property
    def is_expired(self) -> bool:
        return self.elapsed_ratio >= 1.0


@dataclass
class Capabilities:
    camera_available: bool = True
    mic_available: bool = True
    touch_available: bool = True


@dataclass
class Store:
    """전역 상태 저장소 – 단일 인스턴스."""

    # ── authoritative state ──────────────────────────────────
    context_state: ContextState = ContextState.AWAY
    activity_state: ActivityState = ActivityState.IDLE
    active_oneshot: Optional[ActiveOneshot] = None

    # ── extended state ───────────────────────────────────────
    face_present: bool = False
    last_face_seen_at: Optional[float] = None
    last_user_evidence_at: Optional[float] = None
    last_interaction_at: Optional[float] = None
    away_started_at: Optional[float] = field(default_factory=time.time)
    active_executing_kind: Optional[ExecutingKind] = None
    deferred_intent: Optional[Dict[str, Any]] = None

    # ── runtime resources ────────────────────────────────────
    timers: Dict[str, Any] = field(default_factory=dict)
    inflight_requests: Dict[str, Any] = field(default_factory=dict)
    capabilities: Capabilities = field(default_factory=Capabilities)

    # ── snapshot ─────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        """디버그/로깅용 상태 스냅샷."""
        return {
            "context": self.context_state.value,
            "activity": self.activity_state.value,
            "oneshot": self.active_oneshot.name.value if self.active_oneshot else None,
            "face_present": self.face_present,
            "executing_kind": self.active_executing_kind.value if self.active_executing_kind else None,
            "deferred_intent": self.deferred_intent,
        }
