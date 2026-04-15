from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import yaml


@dataclass(frozen=True, slots=True)
class SceneAsset:
    overlay: str | None = None
    sfx_names: tuple[str, ...] = ()
    tts_messages: tuple[str, ...] = ()


@lru_cache(maxsize=4)
def load_scene_assets(path: str = "configs/scenes.yaml") -> dict[str, SceneAsset]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        data = {}
    scene_map = data.get("scenes", {})
    assets: dict[str, SceneAsset] = {}
    for name, config in scene_map.items():
        config = config or {}
        assets[name] = SceneAsset(
            overlay=config.get("overlay"),
            sfx_names=tuple(config.get("sfx", []) or []),
            tts_messages=tuple(config.get("tts", []) or []),
        )
    return assets
