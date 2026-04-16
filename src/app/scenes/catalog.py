from __future__ import annotations

from typing import Callable

from src.app.scenes.assets import load_scene_assets
from src.app.scenes.builders import (
    SceneBlueprint,
    default_scene,
    finger_gun_reaction,
    game_direction,
    petting_reaction,
    peekaboo_reaction,
    sleep_mode_loop,
    smarthome_feedback,
    startled_then_track,
    tap_attention,
    take_photo_countdown,
    wave_greeting,
    welcome_back,
)


SceneBuilder = Callable[..., SceneBlueprint]


SCENE_CATALOG: dict[str, SceneBuilder] = {
    "startled_then_track": startled_then_track,
    "welcome_back": welcome_back,
    "sleep_mode_loop": sleep_mode_loop,
    "take_photo_countdown": take_photo_countdown,
    "smarthome_feedback": smarthome_feedback,
    "wave_greeting": wave_greeting,
    "finger_gun_reaction": finger_gun_reaction,
    "peekaboo_reaction": peekaboo_reaction,
    "tap_attention": tap_attention,
    "game_direction": game_direction,
    "petting_reaction": petting_reaction,
    "default_scene": default_scene,
}


def build_scene_blueprint(name: str) -> SceneBlueprint:
    assets = load_scene_assets()
    builder = SCENE_CATALOG.get(name, default_scene)
    return builder(assets.get(name))
