"""Asset loader — resolves asset names to paths with fallback chain.

Resolution priority:

1. ``<repo>/assets/<category>/<name>`` (real asset)
2. ``<repo>/assets/_dummy/<category>/<name>`` (placeholder from T-077)
3. ``None`` — the renderer / SFX player should use
   :mod:`fallback_primitives` (T-079) or log-only playback instead.

The loader is cache-backed so repeated queries during a render tick are
effectively free. Logs a warning the **first** time each asset falls back
to the dummy layer so developers notice missing production assets without
spam.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

_log = logging.getLogger(__name__)


class AssetLoader:
    def __init__(self, repo_root: Path) -> None:
        self._real_root = repo_root / "assets"
        self._dummy_root = repo_root / "assets" / "_dummy"
        self._cache: Dict[str, Optional[Path]] = {}
        self._warned_fallback: set[str] = set()
        self._warned_missing: set[str] = set()

    # -- core resolution ----------------------------------------------------
    def resolve(self, category: str, name: str) -> Optional[Path]:
        """Return the best available path, or ``None`` if not found at all."""
        key = f"{category}/{name}"
        if key in self._cache:
            return self._cache[key]

        real = self._real_root / category / name
        if real.is_file():
            self._cache[key] = real
            return real

        dummy = self._dummy_root / category / name
        if dummy.is_file():
            if key not in self._warned_fallback:
                _log.info("asset %s falling back to _dummy", key)
                self._warned_fallback.add(key)
            self._cache[key] = dummy
            return dummy

        if key not in self._warned_missing:
            _log.warning("asset %s missing in both real and _dummy layers", key)
            self._warned_missing.add(key)
        self._cache[key] = None
        return None

    # -- typed convenience --------------------------------------------------
    def expression(self, mood_name: str) -> Optional[Path]:
        return self.resolve("expressions", f"{mood_name}.png")

    def ui_icon(self, slot: str) -> Optional[Path]:
        return self.resolve("ui", f"{slot}.png")

    def animation_frame(self, animation: str, frame: int) -> Optional[Path]:
        return self.resolve("animations", f"{animation}_{frame}.png")

    def sound(self, slot: str) -> Optional[Path]:
        return self.resolve("sounds", f"{slot}.wav")

    # -- housekeeping -------------------------------------------------------
    def invalidate(self) -> None:
        self._cache.clear()


def default_loader() -> AssetLoader:
    """Create a loader rooted at the repository this file lives in."""
    # src/app/adapters/display/asset_loader.py → repo root is five parents up.
    return AssetLoader(Path(__file__).resolve().parents[4])
