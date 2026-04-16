"""Scene catalogue — name → :class:`SceneRecipe` lookup.

``EffectPlanner`` / scene executor consults this catalogue to produce the
concrete render / sfx / tts commands. Keeping the map centralised makes
scene names stable identifiers across configs and code.
"""
from __future__ import annotations

from typing import Dict

from .builders import (
    SceneRecipe,
    dance_sequence,
    petting_reaction,
    sleep_mode_loop,
    smarthome_feedback_failure,
    smarthome_feedback_success,
    startled_then_track,
    take_photo_countdown,
    welcome_back,
)


def build_default_catalog() -> Dict[str, SceneRecipe]:
    recipes = (
        startled_then_track(),
        welcome_back(),
        sleep_mode_loop(),
        take_photo_countdown(),
        smarthome_feedback_success(),
        smarthome_feedback_failure(),
        petting_reaction(),
        dance_sequence(),
    )
    return {r.name: r for r in recipes}


DEFAULT_CATALOG: Dict[str, SceneRecipe] = build_default_catalog()


def get(name: str) -> SceneRecipe | None:
    return DEFAULT_CATALOG.get(name)
