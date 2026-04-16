"""Scene Selector — derive :class:`Scene` (Mood + UI) from the FSM state.

Pure function over ``(Context, Activity, Oneshot?)``. This is the single
place that reads the FSM outputs and computes the renderer contract. FSM
transitions must not set mood/UI directly (state-machine.md §9.2).

Spec: state-machine.md §6.1 (Mood priority) and §6.2 (UI matrix).
"""
from __future__ import annotations

from typing import Optional

from .models import (
    ONESHOT_MOOD,
    Activity,
    ActivityKind,
    Context,
    ExecutingKind,
    Mood,
    Oneshot,
    Scene,
    UI,
)


# UI table per state-machine.md §6.2. Rows = ActivityKind or Executing kind,
# columns = Context. Away+Idle is rendered as a dim NormalFace; here that is
# represented by Mood.INACTIVE (the renderer dims when mood is INACTIVE),
# keeping UI a simple enum.
_EXEC_UI_BY_KIND = {
    ExecutingKind.PHOTO: UI.CAMERA_UI,
    ExecutingKind.GAME: UI.GAME_UI,
    ExecutingKind.WEATHER: UI.NORMAL_FACE,
    ExecutingKind.SMARTHOME: UI.NORMAL_FACE,
    ExecutingKind.TIMER_SETUP: UI.NORMAL_FACE,
    ExecutingKind.DANCE: UI.NORMAL_FACE,
}


def derive(
    context: Context,
    activity: Activity,
    active_oneshot: Optional[Oneshot] = None,
) -> Scene:
    mood = _derive_mood(context, activity, active_oneshot)
    ui = _derive_ui(context, activity)
    return Scene(mood=mood, ui=ui)


def _derive_mood(
    context: Context,
    activity: Activity,
    active_oneshot: Optional[Oneshot],
) -> Mood:
    # 1. Alerting override — always alert regardless of context/oneshot.
    if activity.kind is ActivityKind.ALERTING:
        return Mood.ALERT

    # 2. Active oneshot overlays the base mood (state-machine §6.4 note 2:
    #    oneshot survives Executing focus lock by ordering 2 > 3).
    if active_oneshot is not None:
        return ONESHOT_MOOD[active_oneshot.name]

    # 3. Executing focus lock.
    if activity.kind is ActivityKind.EXECUTING:
        return Mood.ATTENTIVE

    # 4. Listening is always attentive.
    if activity.kind is ActivityKind.LISTENING:
        return Mood.ATTENTIVE

    # 5. Idle: context decides.
    if context is Context.AWAY:
        return Mood.INACTIVE
    if context is Context.IDLE:
        return Mood.CALM
    if context is Context.ENGAGED:
        return Mood.ATTENTIVE
    # SLEEPY
    return Mood.SLEEPY


def _derive_ui(context: Context, activity: Activity) -> UI:
    # Alerting overrides everything.
    if activity.kind is ActivityKind.ALERTING:
        return UI.ALERT_UI

    if activity.kind is ActivityKind.LISTENING:
        return UI.LISTENING_UI

    if activity.kind is ActivityKind.EXECUTING:
        # Activity.__post_init__ guarantees executing is not None here.
        return _EXEC_UI_BY_KIND[activity.executing]  # type: ignore[index]

    # Idle: Context decides.
    if context is Context.SLEEPY:
        return UI.SLEEP_UI
    # Away / Idle / Engaged all render NormalFace; the Away case is dimmed
    # via Mood.INACTIVE in the mood branch above.
    return UI.NORMAL_FACE
