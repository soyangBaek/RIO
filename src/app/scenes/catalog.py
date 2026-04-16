"""T-057: Scene catalog – 모든 씬 목록 + 실행 정보.

씬 이름 → (에셋, 동작) 조합. SceneAssets + SceneBuilder 연결.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.app.scenes.assets import SceneAssetSet, SceneAssets
from src.app.scenes.builders import SceneBuilder


@dataclass
class SceneSpec:
    """씬 실행 명세."""
    name: str
    assets: SceneAssetSet
    # 추가 메타 (향후 확장)
    looping: bool = False
    interruptible: bool = True


class SceneCatalog:
    """씬 카탈로그 – 전체 씬 목록 관리."""

    def __init__(self, scenes_config: Optional[Dict[str, Any]] = None) -> None:
        self._assets = SceneAssets(scenes_config)
        self._builder = SceneBuilder()

    def get_scene(self, scene_name: str) -> SceneSpec:
        """씬 이름으로 실행 명세 조회."""
        asset_set = self._assets.get(scene_name)
        looping = scene_name in ("sleep_mode_loop", "dance_mode", "game_mode")
        interruptible = scene_name not in ("take_photo_countdown",)
        return SceneSpec(
            name=scene_name,
            assets=asset_set,
            looping=looping,
            interruptible=interruptible,
        )

    def resolve_and_get(
        self,
        mood,
        ui,
        active_oneshot=None,
        executing_kind=None,
    ) -> SceneSpec:
        """상태로부터 씬 결정 + 명세 반환."""
        scene_name = self._builder.resolve_scene(mood, ui, active_oneshot, executing_kind)
        return self.get_scene(scene_name)

    def all_scene_names(self) -> List[str]:
        return list(self._assets.all_scenes().keys())

    @property
    def builder(self) -> SceneBuilder:
        return self._builder
