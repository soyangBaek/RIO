"""T-019: Display renderer – 3-layer 합성 + 화면 출력.

layers + eye_tracking + hud 를 조합하여 실제 화면에 렌더링.
MVP에서는 pygame 기반. 하드웨어 없으면 headless fallback.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from src.app.adapters.display.eye_tracking import EyeTracker
from src.app.adapters.display.hud import HudManager
from src.app.adapters.display.layers import LayerStack, LayerType
from src.app.core.state.models import Mood, UILayout

logger = logging.getLogger(__name__)

# Mood → 표정 이름 매핑
_MOOD_EXPRESSION = {
    Mood.ALERT: "alert",
    Mood.STARTLED: "startled",
    Mood.HAPPY: "happy",
    Mood.WELCOME: "welcome",
    Mood.CONFUSED: "confused",
    Mood.ATTENTIVE: "attentive",
    Mood.CALM: "neutral",
    Mood.SLEEPY: "sleepy",
}

# UILayout → overlay 매핑
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
    """

    def __init__(self, width: int = 480, height: int = 320, headless: bool = False) -> None:
        self._width = width
        self._height = height
        self._headless = headless
        self._layers = LayerStack()
        self._eye_tracker = EyeTracker()
        self._hud = HudManager()
        self._screen = None
        self._initialized = False

    def initialize(self) -> None:
        """디스플레이 초기화."""
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
        except ImportError:
            logger.warning("pygame not available – falling back to headless")
            self._headless = True
            self._initialized = True

    def apply_scene(self, mood: Mood, ui: UILayout) -> None:
        """Scene Selector 결과를 레이어에 반영."""
        # Core Face: 표정
        expression = _MOOD_EXPRESSION.get(mood, "neutral")
        self._layers.set_expression(expression)

        # Dimming for Away
        self._layers.set_dim(ui == UILayout.NORMAL_FACE_DIM)

        # Action Overlay
        overlay = _UI_OVERLAY.get(ui)
        self._layers.set_overlay(overlay)

        # HUD 아이템 갱신
        self._layers.set_hud_items(self._hud.get_visible_items())

    def update_eye_position(self, center_x: float, center_y: float) -> None:
        """vision.face.moved 좌표 수신."""
        self._eye_tracker.update_face_center(center_x, center_y)

    def on_face_lost(self) -> None:
        self._eye_tracker.on_face_lost()

    def render(self) -> None:
        """한 프레임 렌더링."""
        if not self._initialized:
            return

        # eye tick
        eye_pos = self._eye_tracker.tick()

        if self._headless:
            return

        # pygame 렌더링
        try:
            import pygame
            if self._screen is None:
                return

            composed = self._layers.compose()

            # 배경
            face_content = composed.get("core_face")
            opacity = face_content.opacity if face_content else 1.0
            bg_brightness = int(40 * opacity)
            self._screen.fill((bg_brightness, bg_brightness, bg_brightness + 10))

            # 간단한 눈 렌더링 (placeholder)
            ex = int(eye_pos.x * self._width)
            ey = int(eye_pos.y * self._height)
            pygame.draw.circle(self._screen, (255, 255, 255), (ex - 40, ey), 20)
            pygame.draw.circle(self._screen, (255, 255, 255), (ex + 40, ey), 20)

            pygame.display.flip()
        except Exception:
            logger.debug("Render frame skipped", exc_info=True)

    @property
    def hud(self) -> HudManager:
        return self._hud

    @property
    def eye_tracker(self) -> EyeTracker:
        return self._eye_tracker

    def shutdown(self) -> None:
        if not self._headless:
            try:
                import pygame
                pygame.quit()
            except Exception:
                pass
        self._initialized = False
