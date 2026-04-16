"""Sound effect player.

Scenes use :meth:`SFXPlayer.play` with a slot name (``shutter``,
``success``, ``fail``, ``startle``, ``snore``, ``satisfaction``). The
player resolves the slot through the :class:`AssetLoader` (T-078) so real
WAV files take precedence over the dummy tones produced by T-077.

Three backends are provided:

* :class:`PygameMixerSFX` — preferred when ``pygame`` is installed.
  Handles overlapping playback via multiple mixer channels.
* :class:`AplaySFX` — spawns ``aplay`` for each file (ALSA). Good enough
  for Raspberry Pi images without pygame.
* :class:`NullSFX` — no-op; logs only.

The default factory :func:`make_player` picks the first backend that
initialises successfully.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Protocol

from ..display.asset_loader import AssetLoader

_log = logging.getLogger(__name__)


class SFXBackend(Protocol):
    def play_file(self, path: Path) -> None: ...
    def stop_all(self) -> None: ...


class NullSFX:
    def play_file(self, path: Path) -> None:
        _log.info("NullSFX(play): %s", path.name)

    def stop_all(self) -> None:
        pass


class AplaySFX:
    """Minimal ALSA backend. Spawns ``aplay`` per file (fire-and-forget)."""

    def __init__(self) -> None:
        self._available = shutil.which("aplay") is not None
        if not self._available:
            _log.info("aplay not found; AplaySFX will silently no-op")

    def play_file(self, path: Path) -> None:
        if not self._available:
            return
        try:
            subprocess.Popen(
                ["aplay", "-q", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            _log.exception("aplay invocation failed for %s", path)

    def stop_all(self) -> None:
        # No tracking of child processes — they finish quickly on their own.
        pass


class PygameMixerSFX:
    def __init__(self) -> None:
        self._sounds: dict[str, "pygame.mixer.Sound"] = {}  # noqa: F821
        try:
            import pygame  # type: ignore
            pygame.mixer.init()
            self._pygame = pygame
            self._ok = True
        except Exception as e:  # pragma: no cover - hardware dependent
            _log.info("pygame mixer unavailable (%s)", e)
            self._ok = False

    def play_file(self, path: Path) -> None:
        if not self._ok:
            return
        try:
            key = str(path)
            snd = self._sounds.get(key)
            if snd is None:
                snd = self._pygame.mixer.Sound(key)
                self._sounds[key] = snd
            snd.play()
        except Exception:  # pragma: no cover - hardware dependent
            _log.exception("pygame mixer play failed for %s", path)

    def stop_all(self) -> None:
        if self._ok:
            self._pygame.mixer.stop()


def make_backend() -> SFXBackend:
    """Pick the first SFX backend that initialises successfully."""
    try:
        pg = PygameMixerSFX()
        if pg._ok:
            return pg
    except Exception:  # pragma: no cover
        pass
    aplay = AplaySFX()
    if aplay._available:
        return aplay
    return NullSFX()


class SFXPlayer:
    def __init__(
        self,
        loader: AssetLoader,
        backend: Optional[SFXBackend] = None,
    ) -> None:
        self._loader = loader
        self._backend = backend if backend is not None else make_backend()

    def play(self, slot: str) -> bool:
        """Play the SFX for ``slot``. Returns ``True`` if a file was found."""
        path = self._loader.sound(slot)
        if path is None:
            _log.info("SFX %s missing; silent", slot)
            return False
        self._backend.play_file(path)
        return True

    def stop_all(self) -> None:
        self._backend.stop_all()
