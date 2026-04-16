"""T-030: Effect planner – 상태 전이와 씬 변경을 출력 명령으로 변환.

reducers 결과 → display/speaker/service adapter 명령 계획.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    Mood,
    OneshotName,
    UILayout,
)
from src.app.core.state.reducers import ReducerResult

logger = logging.getLogger(__name__)


@dataclass
class DisplayCommand:
    """디스플레이 명령."""
    mood: str = ""
    ui: str = ""
    dim: bool = False
    search_indicator: bool = False


@dataclass
class SoundCommand:
    """사운드 재생 명령."""
    sound_name: str = ""
    tts_text: Optional[str] = None


@dataclass
class ExecutionCommand:
    """도메인 실행 명령."""
    kind: str = ""
    intent: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EffectPlan:
    """한 턴의 출력 계획."""
    display: Optional[DisplayCommand] = None
    sounds: List[SoundCommand] = field(default_factory=list)
    execution: Optional[ExecutionCommand] = None
    hud_updates: List[Dict[str, Any]] = field(default_factory=list)


# Mood → 사운드 매핑
_MOOD_SOUNDS = {
    Mood.STARTLED: "startled",
    Mood.HAPPY: "happy",
    Mood.WELCOME: "welcome",
    Mood.CONFUSED: "failure",
    Mood.ALERT: "alert",
}


class EffectPlanner:
    """상태 변경 결과를 실행 명령으로 변환."""

    def plan(
        self,
        result: ReducerResult,
        executing_kind: Optional[ExecutingKind] = None,
        is_searching: bool = False,
    ) -> EffectPlan:
        """ReducerResult 를 EffectPlan 으로 변환."""
        plan = EffectPlan()

        # ── Display ──────────────────────────────────────────
        plan.display = DisplayCommand(
            mood=result.mood.value,
            ui=result.ui.value,
            dim=(result.ui == UILayout.NORMAL_FACE_DIM),
            search_indicator=is_searching,
        )

        # ── Sounds (oneshot 트리거 시) ───────────────────────
        if result.oneshot_triggered:
            sound = _MOOD_SOUNDS.get(
                Mood(result.oneshot_triggered.value) if hasattr(result.oneshot_triggered, 'value') else None
            )
            # OneshotName → Mood 매핑
            oneshot_sound_map = {
                OneshotName.STARTLED: "startled",
                OneshotName.HAPPY: "happy",
                OneshotName.WELCOME: "welcome",
                OneshotName.CONFUSED: "failure",
            }
            sound = oneshot_sound_map.get(result.oneshot_triggered)
            if sound:
                plan.sounds.append(SoundCommand(sound_name=sound))

        # Alerting 진입 시 alert 사운드
        if result.activity_changed and result.new_activity == ActivityState.ALERTING:
            plan.sounds.append(SoundCommand(sound_name="alert"))

        # ── Execution (Activity → Executing 진입 시) ─────────
        if (
            result.activity_changed
            and result.new_activity == ActivityState.EXECUTING
            and result.new_executing_kind
        ):
            plan.execution = ExecutionCommand(
                kind=result.new_executing_kind.value,
            )

        return plan
