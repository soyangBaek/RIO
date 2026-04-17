from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.app.adapters.display.hud import build_hud_message
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ActivityState, DerivedScene, ReductionResult
from src.app.domains.behavior.executor_registry import ExecutionRequest
from src.app.scenes.catalog import build_scene_blueprint


@dataclass(slots=True)
class EffectPlan:
    scene_key: str
    scene: DerivedScene
    render: bool = True
    hud_message: str | None = None
    sfx_names: list[str] = field(default_factory=list)
    tts_messages: list[str] = field(default_factory=list)
    executor_request: ExecutionRequest | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _scene_key(result: ReductionResult, event: Event) -> str:
    if event.topic == topics.VISION_GESTURE_DETECTED:
        gesture = event.payload.get("gesture")
        if gesture == "wave":
            return "wave_greeting"
        if gesture == "finger_gun":
            return "finger_gun_reaction"
        if gesture == "peekaboo":
            return "peekaboo_reaction"
        if gesture in {"head_left", "head_right"}:
            return "game_direction"
    if event.topic == topics.TOUCH_TAP_DETECTED:
        return "tap_attention"
    if event.topic == topics.TOUCH_STROKE_DETECTED:
        return "petting_reaction"
    if result.triggered_oneshot is not None:
        mapping = {
            "startled": "startled_then_track",
            "welcome": "welcome_back",
            "happy": "petting_reaction",
        }
        return mapping.get(result.triggered_oneshot.name.value, "default")
    kind = result.current.extended.active_executing_kind
    if kind == ActionKind.PHOTO:
        return "take_photo_countdown"
    if result.scene.ui.value == "SleepUI":
        return "sleep_mode_loop"
    if event.topic == topics.SMARTHOME_RESULT:
        return "smarthome_feedback"
    return "default_scene"


def _executor_request(result: ReductionResult, event: Event) -> ExecutionRequest | None:
    previous_kind = result.previous.extended.active_executing_kind
    current_kind = result.current.extended.active_executing_kind
    if current_kind is None:
        return None
    if (
        result.previous.activity_state == ActivityState.EXECUTING
        and result.current.activity_state == ActivityState.EXECUTING
        and previous_kind == current_kind
    ):
        return None
    if event.topic != topics.VOICE_INTENT_DETECTED:
        return None
    intent = event.payload.get("intent")
    if not intent:
        return None
    return ExecutionRequest(
        kind=current_kind,
        intent=str(intent),
        payload=dict(event.payload),
        trace_id=event.trace_id,
    )


def _tts_messages(event: Event) -> list[str]:
    if event.topic == topics.TIMER_EXPIRED:
        label = event.payload.get("label") or "Timer"
        return [f"{label} time is up."]
    if event.topic == topics.VISION_GESTURE_DETECTED:
        gesture = event.payload.get("gesture")
        if gesture == "wave":
            return ["Hello!"]
        if gesture == "peekaboo":
            return ["Peekaboo!"]
        if gesture == "finger_gun":
            return ["Bang!"]
    if event.topic == topics.SMARTHOME_RESULT:
        if event.payload.get("ok"):
            return [event.payload.get("message") or "Command completed."]
        return [event.payload.get("message") or "Command failed."]
    if event.topic == topics.WEATHER_RESULT:
        if not event.payload.get("ok", True):
            return ["Failed to fetch weather."]
        condition = event.payload.get("condition", "Unknown")
        temperature = event.payload.get("temperature_c")
        if temperature is None:
            return [f"Current weather is {condition}."]
        return [f"Current weather is {condition}, temperature {temperature} degrees."]
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == ActionKind.PHOTO.value:
        return ["Photo taken."]
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == ActionKind.GAME.value:
        return ["Entering game mode."]
    if event.topic == topics.TASK_FAILED:
        return [event.payload.get("message") or "Task failed."]
    return []


def _sfx_names(result: ReductionResult, event: Event) -> list[str]:
    names: list[str] = []
    if result.triggered_oneshot is not None:
        names.append(result.triggered_oneshot.name.value)
    if event.topic == topics.TOUCH_TAP_DETECTED:
        names.append("tap")
    elif event.topic == topics.TOUCH_STROKE_DETECTED:
        names.append("happy")
    elif event.topic == topics.VISION_GESTURE_DETECTED:
        gesture = event.payload.get("gesture")
        if gesture == "wave":
            names.append("welcome")
        elif gesture == "finger_gun":
            names.append("startled")
        elif gesture == "peekaboo":
            names.append("happy")
        elif gesture in {"head_left", "head_right"}:
            names.append("game_move")
    elif event.topic == topics.TIMER_EXPIRED:
        names.append("alert")
    elif event.topic == topics.SMARTHOME_RESULT:
        names.append("success" if event.payload.get("ok") else "error")
    elif event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == ActionKind.PHOTO.value:
        names.append("shutter")
    elif event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == ActionKind.GAME.value:
        names.append("success")
    elif event.topic == topics.TASK_FAILED:
        names.append("error")
    return names


def plan_effects(result: ReductionResult, event: Event) -> EffectPlan:
    scene = result.scene
    hud_message = build_hud_message(event)
    scene_key = _scene_key(result, event)
    blueprint = build_scene_blueprint(scene_key)
    if hud_message:
        scene = DerivedScene(
            mood=scene.mood,
            ui=scene.ui,
            search_indicator=scene.search_indicator,
            dimmed=scene.dimmed,
            overlay=scene.overlay or blueprint.overlay,
            hud_message=hud_message,
        )
    elif scene.overlay is None and blueprint.overlay is not None:
        scene = DerivedScene(
            mood=scene.mood,
            ui=scene.ui,
            search_indicator=scene.search_indicator,
            dimmed=scene.dimmed,
            overlay=blueprint.overlay,
            hud_message=scene.hud_message,
        )
    return EffectPlan(
        scene_key=scene_key,
        scene=scene,
        hud_message=hud_message,
        sfx_names=[*blueprint.sfx_names, *_sfx_names(result, event)],
        tts_messages=[*blueprint.tts_messages, *_tts_messages(event)],
        executor_request=_executor_request(result, event),
        metadata={"topic": event.topic},
    )
