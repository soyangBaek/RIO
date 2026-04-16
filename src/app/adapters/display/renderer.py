"""T-019: Display renderer – 3-layer 합성 + 화면 출력.

layers + eye_tracking + face_compositor + hud 를 조합하여 실제 화면에 렌더링.
MVP에서는 pygame 기반. 하드웨어 없으면 headless fallback.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.app.adapters.display.eye_tracking import EyeTracker
from src.app.adapters.display.face_compositor import FaceCompositor
from src.app.adapters.display.hud import HudManager
from src.app.adapters.display.layers import LayerStack, LayerType
from src.app.core.state.models import Mood, UILayout

logger = logging.getLogger(__name__)

_MOOD_EXPRESSION = {
    Mood.ALERT: "alert",
    Mood.STARTLED: "startled",
    Mood.HAPPY: "happy",
    Mood.WELCOME: "welcome",
    Mood.CONFUSED: "confused",
    Mood.ATTENTIVE: "attentive",
    Mood.CALM: "calm",
    Mood.SLEEPY: "sleepy",
}

_UI_OVERLAY = {
    UILayout.LISTENING_UI: "listening",
    UILayout.CAMERA_UI: "camera",
    UILayout.GAME_UI: "game",
    UILayout.ALERT_UI: "alert",
    UILayout.SLEEP_UI: "sleep",
}


class DisplayRenderer:
    """메인 프로세스 디스플레이 어댑터.

    Scene Selector 의 (Mood, UI) 결과를 화면에 반영.
    FaceCompositor로 부품 기반 얼굴 합성 (breathing, blink, saccade 포함).
    """

    def __init__(
        self,
        width: int = 1024,
        height: int = 600,
        headless: bool = False,
        assets_dir: Optional[Path] = None,
    ) -> None:
        self._width = width
        self._height = height
        self._headless = headless
        self._assets_dir = assets_dir or Path("assets")
        self._layers = LayerStack()
        self._eye_tracker = EyeTracker()
        self._hud = HudManager()
        self._face = FaceCompositor(width=width, height=height)
        self._screen = None
        self._initialized = False

    def initialize(self) -> None:
        if self._headless:
            logger.info("Display: headless mode (no screen)")
            self._initialized = True
            return

        try:
            import pygame
            pygame.init()
            self._screen = pygame.display.set_mode((self._width, self._height))
            pygame.display.set_caption("RIO")
            self._initialized = True
            logger.info("Display initialized: %dx%d", self._width, self._height)

            logger.info("BMO face compositor ready (%dx%d)", self._width, self._height)

        except ImportError:
            logger.warning("pygame not available – falling back to headless")
            self._headless = True
            self._initialized = True

    def apply_scene(self, mood: Mood, ui: UILayout) -> None:
        expression = _MOOD_EXPRESSION.get(mood, "calm")
        self._layers.set_expression(expression)
        self._layers.set_dim(ui == UILayout.NORMAL_FACE_DIM)

        overlay = _UI_OVERLAY.get(ui)
        self._layers.set_overlay(overlay)
        self._layers.set_hud_items(self._hud.get_visible_items())

        self._face.set_mood(expression)
        self._face.set_opacity(0.3 if ui == UILayout.NORMAL_FACE_DIM else 1.0)

    def update_eye_position(self, center_x: float, center_y: float) -> None:
        self._eye_tracker.update_face_center(center_x, center_y)

    def on_face_lost(self) -> None:
        self._eye_tracker.on_face_lost()

    def render(self) -> None:
        if not self._initialized:
            return

        eye_pos = self._eye_tracker.tick()
        saccade_x = (eye_pos.x - 0.5) * 2.0
        saccade_y = (eye_pos.y - 0.5) * 2.0
        self._face.set_saccade(saccade_x, saccade_y)

        if self._headless:
            return

        try:
            import pygame
            if self._screen is None:
                return

            self._screen.fill((20, 20, 28))
            self._face.render(self._screen)
            self._render_hud()
            pygame.display.flip()
        except Exception:
            logger.debug("Render frame skipped", exc_info=True)

    def _render_hud(self) -> None:
        import pygame
        if self._screen is None:
            return

        items = self._hud.get_visible_items()
        if not items:
            return

        try:
            font = pygame.font.SysFont("consolas", 14)
        except Exception:
            return

        y_offset = 5
        for item in items:
            text = f"{item.get('icon', '')} {item.get('text', '')}".strip()
            if not text:
                continue
            label = font.render(text, True, (200, 200, 200))
            pos = item.get("position", "top-right")
            if "right" in pos:
                x = self._width - label.get_width() - 8
            else:
                x = 8
            if "bottom" in pos:
                y = self._height - label.get_height() - y_offset
            else:
                y = y_offset
            self._screen.blit(label, (x, y))
            y_offset += label.get_height() + 4

    @property
    def hud(self) -> HudManager:
        return self._hud

    @property
    def eye_tracker(self) -> EyeTracker:
        return self._eye_tracker

    @property
    def face_compositor(self) -> FaceCompositor:
        return self._face

    def shutdown(self) -> None:
        if not self._headless:
            try:
                import pygame
                pygame.quit()
            except Exception:
                pass
        self._initialized = False
