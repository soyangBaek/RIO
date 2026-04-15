from __future__ import annotations

from src.app.adapters.display.eye_tracking import normalized_center_to_eye_offset
from src.app.adapters.display.hud import build_hud_message
from src.app.adapters.display.layers import FaceLayer, HudLayer, OverlayLayer, RenderFrame
from src.app.core.events.models import Event
from src.app.core.state.models import DerivedScene


class Renderer:
    """Headless renderer that builds the three-layer frame description."""

    def __init__(self) -> None:
        self.history: list[RenderFrame] = []

    def render(
        self,
        scene: DerivedScene,
        *,
        event: Event | None = None,
        face_center: tuple[float, float] | None = None,
    ) -> RenderFrame:
        hud = HudLayer(
            message=build_hud_message(event) if event else scene.hud_message,
            search_indicator=scene.search_indicator,
        )
        overlay_name = scene.overlay
        if overlay_name is None and scene.search_indicator:
            overlay_name = "search_indicator"
        frame = RenderFrame(
            face=FaceLayer(
                mood=scene.mood.value,
                eye_offset=normalized_center_to_eye_offset(face_center),
                dimmed=scene.dimmed,
            ),
            overlay=OverlayLayer(name=overlay_name, visible=overlay_name is not None),
            hud=hud,
            ui=scene.ui.value,
        )
        self.history.append(frame)
        return frame

