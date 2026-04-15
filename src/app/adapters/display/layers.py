from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FaceLayer:
    mood: str
    eye_offset: tuple[int, int] = (0, 0)
    dimmed: bool = False


@dataclass(slots=True)
class OverlayLayer:
    name: str | None = None
    visible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HudLayer:
    message: str | None = None
    badges: list[str] = field(default_factory=list)
    search_indicator: bool = False


@dataclass(slots=True)
class RenderFrame:
    face: FaceLayer
    overlay: OverlayLayer
    hud: HudLayer
    ui: str

