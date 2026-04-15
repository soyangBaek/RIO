from __future__ import annotations

from dataclasses import dataclass

from src.app.scenes.assets import SceneAsset


@dataclass(frozen=True, slots=True)
class SceneBlueprint:
    name: str
    overlay: str | None = None
    sfx_names: tuple[str, ...] = ()
    tts_messages: tuple[str, ...] = ()


def _build(name: str, asset: SceneAsset | None) -> SceneBlueprint:
    asset = asset or SceneAsset()
    return SceneBlueprint(
        name=name,
        overlay=asset.overlay,
        sfx_names=asset.sfx_names,
        tts_messages=asset.tts_messages,
    )


def startled_then_track(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("startled_then_track", asset)


def welcome_back(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("welcome_back", asset)


def sleep_mode_loop(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("sleep_mode_loop", asset)


def take_photo_countdown(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("take_photo_countdown", asset)


def smarthome_feedback(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("smarthome_feedback", asset)


def petting_reaction(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("petting_reaction", asset)


def default_scene(asset: SceneAsset | None = None) -> SceneBlueprint:
    return _build("default_scene", asset)
