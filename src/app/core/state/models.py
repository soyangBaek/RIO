from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ContextState(StrEnum):
    AWAY = "Away"
    IDLE = "Idle"
    ENGAGED = "Engaged"
    SLEEPY = "Sleepy"


class ActivityState(StrEnum):
    IDLE = "Idle"
    LISTENING = "Listening"
    EXECUTING = "Executing"
    ALERTING = "Alerting"


class ActionKind(StrEnum):
    WEATHER = "weather"
    PHOTO = "photo"
    SMARTHOME = "smarthome"
    TIMER_SETUP = "timer_setup"
    GAME = "game"
    DANCE = "dance"


class Mood(StrEnum):
    INACTIVE = "inactive"
    CALM = "calm"
    ATTENTIVE = "attentive"
    SLEEPY = "sleepy"
    ALERT = "alert"
    STARTLED = "startled"
    CONFUSED = "confused"
    WELCOME = "welcome"
    HAPPY = "happy"


class UIState(StrEnum):
    NORMAL_FACE = "NormalFace"
    LISTENING_UI = "ListeningUI"
    CAMERA_UI = "CameraUI"
    GAME_UI = "GameUI"
    ALERT_UI = "AlertUI"
    SLEEP_UI = "SleepUI"


class OneshotName(StrEnum):
    STARTLED = "startled"
    CONFUSED = "confused"
    WELCOME = "welcome"
    HAPPY = "happy"


INTENT_TO_ACTION_KIND: dict[str, ActionKind] = {
    "dance.start": ActionKind.DANCE,
    "camera.capture": ActionKind.PHOTO,
    "ui.game_mode.enter": ActionKind.GAME,
    "timer.create": ActionKind.TIMER_SETUP,
    "weather.current": ActionKind.WEATHER,
    "smarthome.aircon.on": ActionKind.SMARTHOME,
    "smarthome.aircon.off": ActionKind.SMARTHOME,
    "smarthome.aircon.set_temperature": ActionKind.SMARTHOME,
    "smarthome.light.on": ActionKind.SMARTHOME,
    "smarthome.light.off": ActionKind.SMARTHOME,
    "smarthome.robot_cleaner.stop": ActionKind.SMARTHOME,
    "smarthome.robot_cleaner.start": ActionKind.SMARTHOME,
    "smarthome.tv.on": ActionKind.SMARTHOME,
    "smarthome.tv.off": ActionKind.SMARTHOME,
    "smarthome.music.play": ActionKind.SMARTHOME,
    "smarthome.music.stop": ActionKind.SMARTHOME,
}


def intent_to_action_kind(intent: str | None) -> ActionKind | None:
    if not intent:
        return None
    return INTENT_TO_ACTION_KIND.get(intent)


@dataclass(slots=True)
class CapabilityState:
    camera_available: bool = True
    mic_available: bool = True
    touch_available: bool = True
    speaker_available: bool = True


@dataclass(slots=True)
class TimerRecord:
    timer_id: str
    label: str
    due_at: datetime
    created_at: datetime
    delay_seconds: float


@dataclass(slots=True)
class Oneshot:
    name: OneshotName
    priority: int
    duration_ms: int
    started_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def elapsed_ratio(self, now: datetime) -> float:
        elapsed = max((now - self.started_at).total_seconds() * 1000.0, 0.0)
        if self.duration_ms <= 0:
            return 1.0
        return min(elapsed / self.duration_ms, 1.0)

    def is_expired(self, now: datetime) -> bool:
        return self.elapsed_ratio(now) >= 1.0


@dataclass(slots=True)
class ExtendedState:
    face_present: bool = False
    last_face_seen_at: datetime | None = None
    last_face_lost_at: datetime | None = None
    last_user_evidence_at: datetime | None = None
    last_interaction_at: datetime | None = None
    away_started_at: datetime | None = None
    active_executing_kind: ActionKind | None = None
    deferred_intent: dict[str, Any] | None = None
    ui_mode: str | None = None
    timers: dict[str, TimerRecord] = field(default_factory=dict)
    inflight_requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    capabilities: CapabilityState = field(default_factory=CapabilityState)
    previous_context_state: ContextState | None = None
    sleepy_with_face: bool = False


@dataclass(slots=True)
class DerivedScene:
    mood: Mood
    ui: UIState
    search_indicator: bool = False
    dimmed: bool = False
    overlay: str | None = None
    hud_message: str | None = None


@dataclass(slots=True)
class RuntimeState:
    context_state: ContextState = ContextState.AWAY
    activity_state: ActivityState = ActivityState.IDLE
    active_oneshot: Oneshot | None = None
    extended: ExtendedState = field(default_factory=ExtendedState)


@dataclass(slots=True)
class ReductionResult:
    previous: RuntimeState
    current: RuntimeState
    scene: DerivedScene
    emitted_events: list[Any] = field(default_factory=list)
    triggered_oneshot: Oneshot | None = None
