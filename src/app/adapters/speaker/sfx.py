"""T-022: 효과음 재생 어댑터.

사운드 파일 경로 기반 재생. pygame.mixer 또는 fallback.
더미 에셋은 빈 파일로 처리.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 기본 사운드 매핑 (assets/sounds/)
DEFAULT_SOUNDS: Dict[str, str] = {
    "shutter": "assets/sounds/shutter.wav",
    "success": "assets/sounds/success.wav",
    "failure": "assets/sounds/failure.wav",
    "startled": "assets/sounds/startled.wav",
    "snore": "assets/sounds/snore.wav",
    "happy": "assets/sounds/happy.wav",
    "alert": "assets/sounds/alert.wav",
    "welcome": "assets/sounds/welcome.wav",
}


class SfxPlayer:
    """효과음 재생."""

    def __init__(self, base_path: str = ".", headless: bool = False) -> None:
        self._base = Path(base_path)
        self._headless = headless
        self._initialized = False
        self._sounds: Dict[str, str] = dict(DEFAULT_SOUNDS)

    def initialize(self) -> None:
        if self._headless:
            self._initialized = True
            return
        try:
            import pygame.mixer
            pygame.mixer.init()
            self._initialized = True
            logger.info("SfxPlayer initialized")
        except (ImportError, Exception) as e:
            logger.warning("SfxPlayer fallback to headless: %s", e)
            self._headless = True
            self._initialized = True

    def play(self, sound_name: str) -> None:
        """사운드 이름으로 재생."""
        if not self._initialized:
            self.initialize()

        path = self._sounds.get(sound_name)
        if not path:
            logger.debug("Unknown sound: %s", sound_name)
            return

        full_path = self._base / path
        if self._headless:
            logger.debug("SFX (headless): %s", sound_name)
            return

        try:
            import pygame.mixer
            if full_path.exists():
                sound = pygame.mixer.Sound(str(full_path))
                sound.play()
            else:
                logger.debug("Sound file not found (dummy): %s", full_path)
        except Exception as e:
            logger.debug("SFX play error: %s", e)

    def play_file(self, file_path: str) -> None:
        """파일 경로 직접 재생."""
        if self._headless:
            logger.debug("SFX file (headless): %s", file_path)
            return
        try:
            import pygame.mixer
            if os.path.exists(file_path):
                sound = pygame.mixer.Sound(file_path)
                sound.play()
        except Exception as e:
            logger.debug("SFX file play error: %s", e)

    def shutdown(self) -> None:
        if not self._headless:
            try:
                import pygame.mixer
                pygame.mixer.quit()
            except Exception:
                pass
