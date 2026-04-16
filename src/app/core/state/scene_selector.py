"""T-011: Scene Selector – (Context, Activity, active_oneshot) → (Mood, UI) 순수 함수.

state-machine.md §6 기준.
§6.1 Mood 파생 우선순위, §6.2 UI 매핑 테이블, §6.4 override 규칙.
"""
from __future__ import annotations

from typing import Optional, Tuple

from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    Mood,
    OneshotName,
    UILayout,
)
from src.app.core.state.store import ActiveOneshot

# ── Oneshot → Mood 매핑 ─────────────────────────────────────
_ONESHOT_MOOD = {
    OneshotName.STARTLED: Mood.STARTLED,
    OneshotName.CONFUSED: Mood.CONFUSED,
    OneshotName.WELCOME: Mood.WELCOME,
    OneshotName.HAPPY: Mood.HAPPY,
}


def derive_scene(
    context: ContextState,
    activity: ActivityState,
    active_oneshot: Optional[ActiveOneshot],
    executing_kind: Optional[ExecutingKind] = None,
) -> Tuple[Mood, UILayout]:
    """순수 함수: 현재 상태로부터 (Mood, UILayout)을 파생."""
    mood = _derive_mood(context, activity, active_oneshot)
    ui = _derive_ui(context, activity, executing_kind)
    return mood, ui


# ── Mood 파생 (§6.1 우선순위) ────────────────────────────────
def _derive_mood(
    context: ContextState,
    activity: ActivityState,
    active_oneshot: Optional[ActiveOneshot],
) -> Mood:
    # 1. Alerting override
    if activity == ActivityState.ALERTING:
        return Mood.ALERT

    # 2. Active oneshot
    if active_oneshot is not None and not active_oneshot.is_expired:
        return _ONESHOT_MOOD.get(active_oneshot.name, Mood.CALM)

    # 3. Executing focus lock
    if activity == ActivityState.EXECUTING:
        return Mood.ATTENTIVE

    # 4. Listening
    if activity == ActivityState.LISTENING:
        return Mood.ATTENTIVE

    # 5. Idle → Context 기반
    if context == ContextState.AWAY:
        return Mood.INACTIVE
    if context == ContextState.IDLE:
        return Mood.CALM
    if context == ContextState.ENGAGED:
        return Mood.ATTENTIVE
    if context == ContextState.SLEEPY:
        return Mood.SLEEPY

    return Mood.CALM


# ── UI 파생 (§6.2 완전 매핑 테이블) ─────────────────────────
def _derive_ui(
    context: ContextState,
    activity: ActivityState,
    executing_kind: Optional[ExecutingKind],
) -> UILayout:
    # Alerting override
    if activity == ActivityState.ALERTING:
        return UILayout.ALERT_UI

    # Listening
    if activity == ActivityState.LISTENING:
        return UILayout.LISTENING_UI

    # Executing(kind)
    if activity == ActivityState.EXECUTING and executing_kind:
        if executing_kind == ExecutingKind.PHOTO:
            return UILayout.CAMERA_UI
        if executing_kind == ExecutingKind.GAME:
            return UILayout.GAME_UI
        # weather, smarthome, timer_setup, dance → NormalFace
        return UILayout.NORMAL_FACE

    # Idle → Context 기반
    if context == ContextState.AWAY:
        return UILayout.NORMAL_FACE_DIM
    if context == ContextState.SLEEPY:
        return UILayout.SLEEP_UI
    return UILayout.NORMAL_FACE
