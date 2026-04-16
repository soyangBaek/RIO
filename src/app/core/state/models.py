"""T-005: 상태 모델 정의.

Context FSM, Activity FSM, Executing kinds, Oneshot, Mood, UI 열거형.
state-machine.md 전체 반영.
"""
from __future__ import annotations

from enum import Enum, auto


# ── Context FSM ─────────────────────────────────────────────
class ContextState(Enum):
    AWAY = "Away"
    IDLE = "Idle"
    ENGAGED = "Engaged"
    SLEEPY = "Sleepy"


# ── Activity FSM ────────────────────────────────────────────
class ActivityState(Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    EXECUTING = "Executing"
    ALERTING = "Alerting"


# ── Executing kind 파라미터 ─────────────────────────────────
class ExecutingKind(Enum):
    WEATHER = "weather"
    PHOTO = "photo"
    SMARTHOME = "smarthome"
    TIMER_SETUP = "timer_setup"
    GAME = "game"
    DANCE = "dance"


# ── Oneshot 이벤트 이름 ─────────────────────────────────────
class OneshotName(Enum):
    STARTLED = "startled"
    CONFUSED = "confused"
    WELCOME = "welcome"
    HAPPY = "happy"


# ── Mood (표정 파생) ────────────────────────────────────────
class Mood(Enum):
    ALERT = "alert"
    STARTLED = "startled"
    HAPPY = "happy"
    WELCOME = "welcome"
    CONFUSED = "confused"
    ATTENTIVE = "attentive"
    CALM = "calm"
    SLEEPY = "sleepy"
    INACTIVE = "inactive"


# ── UI 레이아웃 (Scene Selector 출력) ───────────────────────
class UILayout(Enum):
    NORMAL_FACE = "NormalFace"
    NORMAL_FACE_DIM = "NormalFace(dim)"
    LISTENING_UI = "ListeningUI"
    CAMERA_UI = "CameraUI"
    GAME_UI = "GameUI"
    SLEEP_UI = "SleepUI"
    ALERT_UI = "AlertUI"
