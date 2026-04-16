"""T-055: Scene assets – 씬별 에셋 참조.

각 scene이 사용하는 표정/사운드/애니메이션 에셋 매핑.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SceneAssetSet:
    """하나의 씬에 사용되는 에셋 묶음."""
    expression: str = "neutral"
    sound: Optional[str] = None
    animation: Optional[str] = None
    overlay: Optional[str] = None
    duration_ms: float = 0  # 0 = 상시


# 씬별 기본 에셋 매핑
DEFAULT_SCENE_ASSETS: Dict[str, SceneAssetSet] = {
    "startled_then_track": SceneAssetSet(
        expression="startled",
        sound="startled",
        duration_ms=600,
    ),
    "welcome_back": SceneAssetSet(
        expression="welcome",
        sound="welcome",
        animation="welcome_wave",
        duration_ms=1500,
    ),
    "sleep_mode_loop": SceneAssetSet(
        expression="sleepy",
        sound="snore",
        animation="dream",
    ),
    "take_photo_countdown": SceneAssetSet(
        expression="attentive",
        sound="shutter",
        overlay="camera",
    ),
    "smarthome_feedback": SceneAssetSet(
        expression="happy",
        sound="success",
        duration_ms=1000,
    ),
    "petting_reaction": SceneAssetSet(
        expression="happy",
        sound="happy",
        duration_ms=1000,
    ),
    "alert_timer": SceneAssetSet(
        expression="alert",
        sound="alert",
        overlay="alert",
    ),
    "confused_reaction": SceneAssetSet(
        expression="confused",
        sound="failure",
        duration_ms=800,
    ),
    "dance_mode": SceneAssetSet(
        expression="happy",
        animation="dance",
    ),
}


class SceneAssets:
    """씬 에셋 레지스트리."""

    def __init__(self, scenes_config: Optional[Dict[str, Any]] = None) -> None:
        self._assets: Dict[str, SceneAssetSet] = dict(DEFAULT_SCENE_ASSETS)
        if scenes_config:
            self._load_config(scenes_config)

    def _load_config(self, config: Dict[str, Any]) -> None:
        scenes = config.get("scenes", {})
        for name, cfg in scenes.items():
            if isinstance(cfg, dict) and cfg:
                self._assets[name] = SceneAssetSet(
                    expression=cfg.get("expression", "neutral"),
                    sound=cfg.get("sound"),
                    animation=cfg.get("animation"),
                    overlay=cfg.get("overlay"),
                    duration_ms=cfg.get("duration_ms", 0),
                )

    def get(self, scene_name: str) -> SceneAssetSet:
        return self._assets.get(scene_name, SceneAssetSet())

    def all_scenes(self) -> Dict[str, SceneAssetSet]:
        return dict(self._assets)
