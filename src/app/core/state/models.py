"""Typed state models for the RIO state machine.

All enums and dataclasses in this module are the single source of truth for
state shape across ``core/state``, ``domains/behavior``, and the adapters.
Authoritative doc: ``docs/state-machine.md``.

Guiding principles from state-machine.md §1:

- Only two FSM axes exist: ``Context`` and ``Activity``.
- ``Mood`` and ``UI`` are **derived** from the FSMs + active oneshot; they are
  not stored in the main state, they live in :class:`Scene`.
- Transient reactions are not states; they are :class:`Oneshot` events with a
  bounded duration and priority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# -- Context FSM (state-machine.md §3) --------------------------------------
class Context(Enum):
    AWAY = "away"
    IDLE = "idle"
    ENGAGED = "engaged"
    SLEEPY = "sleepy"


# -- Activity FSM (state-machine.md §4) -------------------------------------
class ActivityKind(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    EXECUTING = "executing"
    ALERTING = "alerting"


class ExecutingKind(Enum):
    """Parameter of :attr:`Activity.executing` when :attr:`Activity.kind` is
    :attr:`ActivityKind.EXECUTING`. New features extend this enum and the
    §6.2 table in state-machine.md."""
    PHOTO = "photo"
    WEATHER = "weather"
    SMARTHOME = "smarthome"
    TIMER_SETUP = "timer_setup"
    GAME = "game"
    DANCE = "dance"


@dataclass(frozen=True)
class Activity:
    kind: ActivityKind
    executing: Optional[ExecutingKind] = None

    def __post_init__(self) -> None:
        if self.kind is ActivityKind.EXECUTING and self.executing is None:
            raise ValueError("ActivityKind.EXECUTING requires an ExecutingKind")
        if self.kind is not ActivityKind.EXECUTING and self.executing is not None:
            raise ValueError(
                "executing kind must be None unless ActivityKind is EXECUTING"
            )

    def __str__(self) -> str:
        if self.kind is ActivityKind.EXECUTING:
            return f"Executing({self.executing.value})"  # type: ignore[union-attr]
        return self.kind.value.capitalize()


# -- Scene (derived output, state-machine.md §6) ----------------------------
class Mood(Enum):
    """Facial expression class derived by the Scene Selector.

    ``INACTIVE`` is the ``Away`` + ``Idle`` appearance with eyes closed or
    dim — it replaces a separate "dim" flag on :class:`Scene` and keeps the
    renderer logic table-driven.
    """
    CALM = "calm"
    ATTENTIVE = "attentive"
    SLEEPY = "sleepy"
    ALERT = "alert"
    SURPRISED = "surprised"  # oneshot=startled
    HAPPY = "happy"          # oneshot=happy / welcome success
    CONFUSED = "confused"    # oneshot=confused
    INACTIVE = "inactive"    # Away + Idle


class UI(Enum):
    NORMAL_FACE = "normal_face"
    LISTENING_UI = "listening_ui"
    CAMERA_UI = "camera_ui"
    GAME_UI = "game_ui"
    SLEEP_UI = "sleep_ui"
    ALERT_UI = "alert_ui"


@dataclass(frozen=True)
class Scene:
    mood: Mood
    ui: UI


# -- Oneshot (state-machine.md §5) ------------------------------------------
class OneshotName(Enum):
    STARTLED = "startled"
    CONFUSED = "confused"
    WELCOME = "welcome"
    HAPPY = "happy"


# Default priorities / durations per state-machine.md §5. Runtime tuning lives
# in configs/scenes.yaml; these constants document the baseline so tests and
# the oneshot dispatcher can run without a loaded config.
DEFAULT_ONESHOT_PRIORITY: Dict[OneshotName, int] = {
    OneshotName.STARTLED: 30,
    OneshotName.CONFUSED: 25,
    OneshotName.WELCOME: 20,
    OneshotName.HAPPY: 20,
}

DEFAULT_ONESHOT_DURATION_MS: Dict[OneshotName, int] = {
    OneshotName.STARTLED: 600,
    OneshotName.CONFUSED: 800,
    OneshotName.WELCOME: 1500,
    OneshotName.HAPPY: 1000,
}

ONESHOT_MOOD: Dict[OneshotName, Mood] = {
    OneshotName.STARTLED: Mood.SURPRISED,
    OneshotName.CONFUSED: Mood.CONFUSED,
    OneshotName.WELCOME: Mood.HAPPY,
    OneshotName.HAPPY: Mood.HAPPY,
}


@dataclass(frozen=True)
class Oneshot:
    name: OneshotName
    priority: int
    duration_ms: int
    started_at: float  # monotonic seconds, aligned with Event.timestamp

    @property
    def ends_at(self) -> float:
        return self.started_at + self.duration_ms / 1000.0

    def progress(self, now: float) -> float:
        """Fraction of duration elapsed at ``now`` (clamped to [0, 1])."""
        if self.duration_ms <= 0:
            return 1.0
        ratio = (now - self.started_at) / (self.duration_ms / 1000.0)
        if ratio < 0.0:
            return 0.0
        if ratio > 1.0:
            return 1.0
        return ratio

    def expired_at(self, now: float) -> bool:
        return now >= self.ends_at


# -- Extended state (state-machine.md §3.1) ---------------------------------
@dataclass
class ExtendedState:
    """Non-FSM values required to evaluate transitions and derived situations.

    All timestamps are monotonic seconds (aligned with :attr:`Event.timestamp`)
    to avoid drift from wall-clock adjustments.
    """
    face_present: bool = False
    last_face_seen_at: Optional[float] = None
    last_user_evidence_at: Optional[float] = None
    last_interaction_at: Optional[float] = None
    away_started_at: Optional[float] = None
    activity_started_at: Optional[float] = None
    active_executing_kind: Optional[ExecutingKind] = None
    deferred_intent: Optional[Dict[str, Any]] = None
    timers: Dict[str, Any] = field(default_factory=dict)
    inflight_requests: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, bool] = field(default_factory=dict)


# -- Top-level store payload ------------------------------------------------
@dataclass
class State:
    """The authoritative store value held by :class:`app.core.state.store`.

    :attr:`active_oneshot` is managed by the oneshot dispatcher (T-010); it
    lives alongside the FSM state because the Scene Selector reads all three
    to derive :class:`Scene`.
    """
    context: Context = Context.AWAY
    activity: Activity = field(
        default_factory=lambda: Activity(ActivityKind.IDLE)
    )
    extended: ExtendedState = field(default_factory=ExtendedState)
    active_oneshot: Optional[Oneshot] = None
