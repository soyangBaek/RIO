from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.app.core.config import resolve_repo_path


SFX_FILES: dict[str, str] = {
    "startled": "assets/sounds/shocked-emote.mp3",
    "welcome": "assets/sounds/pleased-emote.mp3",
    "dance": "assets/sounds/dance.mp3",
    "shutter": "assets/sounds/camera_shutter.mp3",
    "alert": "assets/sounds/timer_ring.mp3",
    "timer_registered": "assets/sounds/timer_ring.mp3",
    "success": "assets/sounds/pride-emote.mp3",
    "error": "assets/sounds/surprise-emote.mp3",
    "listening_cue": "assets/sounds/listening_cue.mp3",
    "sleepy": "assets/sounds/sleepy-emote.mp3",
    "angry": "assets/sounds/distress-emote.mp3",
    "lovely": "assets/sounds/love-emote.mp3",
    "weather": "assets/sounds/flourish-emote-animal-crossing.mp3",
    "weather_failed": "assets/sounds/surprise-emote.mp3",
}

# 개별 볼륨 조정 (0.0 ~ 1.0, 기본 1.0)
SFX_VOLUME: dict[str, float] = {
    "sleepy": 1.0,
}


@dataclass(slots=True)
class SFXPlayer:
    """Plays sound effects via pygame.mixer, with a history log for tests."""

    history: list[str] = field(default_factory=list)
    _initialized: bool = False
    _sounds: dict[str, object] = field(default_factory=dict)
    _channels: dict[str, object] = field(default_factory=dict)

    def _ensure_mixer(self) -> bool:
        if self._initialized:
            return True
        try:
            os.environ.setdefault("SDL_AUDIODRIVER", "pulseaudio")
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._initialized = True
            return True
        except Exception:
            return False

    def _load(self, name: str) -> object | None:
        if name in self._sounds:
            return self._sounds[name]
        rel = SFX_FILES.get(name)
        if rel is None:
            return None
        path: Path = resolve_repo_path(rel)
        if not path.exists():
            return None
        try:
            import pygame

            sound = pygame.mixer.Sound(str(path))
        except Exception:
            return None
        self._sounds[name] = sound
        return sound

    def play(self, name: str, *, loops: int = 0) -> str:
        self.history.append(name)
        if name in SFX_FILES and self._ensure_mixer():
            sound = self._load(name)
            if sound is not None:
                try:
                    channel = sound.play(loops=loops)
                    if channel is not None:
                        self._channels[name] = channel
                except Exception:
                    pass
        return name

    def stop(self, name: str) -> None:
        channel = self._channels.pop(name, None)
        if channel is None:
            return
        try:
            channel.stop()
        except Exception:
            pass
