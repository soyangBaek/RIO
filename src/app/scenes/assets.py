"""Scene-level asset slot references.

A "scene" (e.g., ``welcome_back``, ``take_photo_countdown``) is a short
presentation recipe: expression, overlay animation, SFX, optional HUD
widget. This module enumerates the slots the scenes speak in, backed by
:class:`AssetLoader` — real files under ``assets/`` take precedence over
``_dummy/`` placeholders.

The slots here are stable identifiers; see ``configs/scenes.yaml`` for the
actual sequencing and timing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..adapters.display.asset_loader import AssetLoader


@dataclass(frozen=True)
class SceneAssets:
    expression: Optional[Path]
    animation_frames: tuple
    sfx: Optional[Path]


def load_scene(loader: AssetLoader, *, expression: Optional[str] = None,
               animation: Optional[str] = None, animation_frames: int = 2,
               sfx: Optional[str] = None) -> SceneAssets:
    expr = loader.expression(expression) if expression else None
    frames = tuple(
        loader.animation_frame(animation, i) for i in range(animation_frames)
    ) if animation else tuple()
    s = loader.sound(sfx) if sfx else None
    return SceneAssets(expression=expr, animation_frames=frames, sfx=s)
