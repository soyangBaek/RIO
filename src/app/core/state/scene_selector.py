from __future__ import annotations

from src.app.core.state.models import (
    ActionKind,
    ActivityState,
    ContextState,
    DerivedScene,
    ExtendedState,
    Mood,
    Oneshot,
    OneshotName,
    UIState,
)


ONESHOT_TO_MOOD = {
    OneshotName.STARTLED: Mood.STARTLED,
    OneshotName.CONFUSED: Mood.CONFUSED,
    OneshotName.WELCOME: Mood.WELCOME,
    OneshotName.HAPPY: Mood.HAPPY,
}


def _ui_for(activity: ActivityState, context: ContextState, kind: ActionKind | None, ui_mode: str | None) -> UIState:
    if activity == ActivityState.LISTENING:
        return UIState.LISTENING_UI
    if activity == ActivityState.ALERTING:
        return UIState.ALERT_UI
    if activity == ActivityState.EXECUTING:
        if kind == ActionKind.PHOTO:
            return UIState.CAMERA_UI
        if kind == ActionKind.GAME:
            return UIState.GAME_UI
        return UIState.NORMAL_FACE
    if ui_mode == "game":
        return UIState.GAME_UI
    if context == ContextState.SLEEPY:
        return UIState.SLEEP_UI
    return UIState.NORMAL_FACE


def _mood_for(
    context: ContextState,
    activity: ActivityState,
    ui_mode: str | None,
    active_oneshot: Oneshot | None,
) -> Mood:
    if activity == ActivityState.ALERTING:
        return Mood.ALERT
    if active_oneshot is not None:
        return ONESHOT_TO_MOOD[active_oneshot.name]
    if activity in {ActivityState.LISTENING, ActivityState.EXECUTING}:
        return Mood.ATTENTIVE
    if ui_mode == "game":
        return Mood.ATTENTIVE
    if context == ContextState.AWAY:
        return Mood.INACTIVE
    if context == ContextState.IDLE:
        return Mood.CALM
    if context == ContextState.ENGAGED:
        return Mood.ATTENTIVE
    return Mood.SLEEPY


def select_scene(
    context: ContextState,
    activity: ActivityState,
    extended: ExtendedState,
    active_oneshot: Oneshot | None,
) -> DerivedScene:
    ui = _ui_for(activity, context, extended.active_executing_kind, extended.ui_mode)
    mood = _mood_for(context, activity, extended.ui_mode, active_oneshot)
    dimmed = activity == ActivityState.IDLE and context == ContextState.AWAY
    search_indicator = activity == ActivityState.LISTENING and not extended.face_present
    return DerivedScene(
        mood=mood,
        ui=ui,
        search_indicator=search_indicator,
        dimmed=dimmed,
    )
