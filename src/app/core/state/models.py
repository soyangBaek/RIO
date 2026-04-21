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
    ANGRY = "angry"
    LOVELY = "lovely"


INTENT_TO_ACTION_KIND: dict[str, ActionKind] = {
    "dance.start": ActionKind.DANCE,
    "camera.capture": ActionKind.PHOTO,
    "ui.game_mode.enter": ActionKind.GAME,
    "timer.create": ActionKind.TIMER_SETUP,
    "weather.current": ActionKind.WEATHER,
    "smarthome.tv.on": ActionKind.SMARTHOME,
    "smarthome.tv.off": ActionKind.SMARTHOME,
    "smarthome.computer.on": ActionKind.SMARTHOME,
    "smarthome.computer.off": ActionKind.SMARTHOME,
    "smarthome.light.on": ActionKind.SMARTHOME,
    "smarthome.light.off": ActionKind.SMARTHOME,
    "smarthome.indirect_light.on": ActionKind.SMARTHOME,
    "smarthome.indirect_light.off": ActionKind.SMARTHOME,
    "smarthome.robot_cleaner.start": ActionKind.SMARTHOME,
    "smarthome.robot_cleaner.stop": ActionKind.SMARTHOME,
    "smarthome.air_purifier.on": ActionKind.SMARTHOME,
    "smarthome.air_purifier.off": ActionKind.SMARTHOME,
    "smarthome.aircon.on": ActionKind.SMARTHOME,
    "smarthome.aircon.off": ActionKind.SMARTHOME,
    "smarthome.aircon.set_temperature": ActionKind.SMARTHOME,
    "smarthome.heater.on": ActionKind.SMARTHOME,
    "smarthome.heater.off": ActionKind.SMARTHOME,
    "smarthome.heater.set_temperature": ActionKind.SMARTHOME,
    "smarthome.all.off": ActionKind.SMARTHOME,
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

    def copy(self) -> "CapabilityState":
        return CapabilityState(
            camera_available=self.camera_available,
            mic_available=self.mic_available,
            touch_available=self.touch_available,
            speaker_available=self.speaker_available,
        )


@dataclass(slots=True)
class TimerRecord:
    timer_id: str
    label: str
    due_at: datetime
    created_at: datetime
    delay_seconds: float

    def copy(self) -> "TimerRecord":
        return TimerRecord(
            timer_id=self.timer_id,
            label=self.label,
            due_at=self.due_at,
            created_at=self.created_at,
            delay_seconds=self.delay_seconds,
        )


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

    def copy(self) -> "Oneshot":
        return Oneshot(
            name=self.name,
            priority=self.priority,
            duration_ms=self.duration_ms,
            started_at=self.started_at,
            payload=dict(self.payload),
        )


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

    def copy(self) -> "ExtendedState":
        return ExtendedState(
            face_present=self.face_present,
            last_face_seen_at=self.last_face_seen_at,
            last_face_lost_at=self.last_face_lost_at,
            last_user_evidence_at=self.last_user_evidence_at,
            last_interaction_at=self.last_interaction_at,
            away_started_at=self.away_started_at,
            active_executing_kind=self.active_executing_kind,
            deferred_intent=dict(self.deferred_intent) if self.deferred_intent else None,
            ui_mode=self.ui_mode,
            timers={key: value.copy() for key, value in self.timers.items()},
            inflight_requests={key: dict(value) for key, value in self.inflight_requests.items()},
            capabilities=self.capabilities.copy(),
            previous_context_state=self.previous_context_state,
            sleepy_with_face=self.sleepy_with_face,
        )


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

    def copy(self) -> "RuntimeState":
        return RuntimeState(
            context_state=self.context_state,
            activity_state=self.activity_state,
            active_oneshot=self.active_oneshot.copy() if self.active_oneshot is not None else None,
            extended=self.extended.copy(),
        )


@dataclass(slots=True)
class ReductionResult:
    previous: RuntimeState
    current: RuntimeState
    scene: DerivedScene
    emitted_events: list[Any] = field(default_factory=list)
    triggered_oneshot: Oneshot | None = None
