from __future__ import annotations

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

    def play(self, name: str) -> str:
        self.history.append(name)
        if name in SFX_FILES and self._ensure_mixer():
            sound = self._load(name)
            if sound is not None:
                try:
                    channel = sound.play()
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
