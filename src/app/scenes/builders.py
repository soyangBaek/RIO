"""Scene builder helpers.

Produces :class:`SceneRecipe` values — lightweight descriptions of a
presentation sequence. Effect-planning (T-030) consumes them to drive SFX
/ TTS / HUD. Actual animation sequencing is owned by the renderer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..core.state.models import Mood


@dataclass(frozen=True)
class SceneRecipe:
    name: str
    mood: Optional[Mood] = None
    sfx: Optional[str] = None
    tts: Optional[str] = None
    duration_ms: int = 0
    animation: Optional[str] = None
    animation_frames: int = 2


def startled_then_track() -> SceneRecipe:
    """SYS-04 / SYS-10b — surprise reaction to voice without face."""
    return SceneRecipe(
        name="startled_then_track",
        mood=Mood.SURPRISED,
        sfx="startle",
        duration_ms=600,
    )


def welcome_back() -> SceneRecipe:
    return SceneRecipe(
        name="welcome_back",
        mood=Mood.HAPPY,
        animation="welcome_wave",
        duration_ms=1500,
    )


def sleep_mode_loop() -> SceneRecipe:
    return SceneRecipe(
        name="sleep_mode_loop",
        mood=Mood.SLEEPY,
        animation="dream",
        sfx="snore",
        duration_ms=3000,
    )


def take_photo_countdown() -> SceneRecipe:
    return SceneRecipe(
        name="take_photo_countdown",
        mood=Mood.ATTENTIVE,
        duration_ms=3000,
    )


def smarthome_feedback_success() -> SceneRecipe:
    return SceneRecipe(
        name="smarthome_feedback_success",
        mood=Mood.HAPPY,
        sfx="success",
        duration_ms=1000,
    )


def smarthome_feedback_failure() -> SceneRecipe:
    return SceneRecipe(
        name="smarthome_feedback_failure",
        mood=Mood.CONFUSED,
        sfx="fail",
        duration_ms=1000,
    )


def petting_reaction() -> SceneRecipe:
    return SceneRecipe(
        name="petting_reaction",
        mood=Mood.HAPPY,
        sfx="satisfaction",
        duration_ms=1000,
    )


def dance_sequence() -> SceneRecipe:
    return SceneRecipe(
        name="dance_sequence",
        mood=Mood.HAPPY,
        animation="dance",
        duration_ms=3000,
    )
