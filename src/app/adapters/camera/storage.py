"""Photo storage helpers.

Generates a deterministic, human-scannable path inside a base directory
(``captures/YYYY/MM/YYYYMMDD-HHMMSS.jpg``) and creates intermediate
directories on demand. The base directory is provided by ``robot.yaml`` so
deployments can point it at a USB drive, a mounted share, or wherever is
appropriate.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path


class PhotoStorage:
    def __init__(self, base_dir: Path, extension: str = "jpg") -> None:
        self._base = Path(base_dir)
        self._ext = extension.lstrip(".")

    def new_path(self, when: _dt.datetime | None = None) -> Path:
        when = when or _dt.datetime.now()
        sub = self._base / f"{when.year:04d}" / f"{when.month:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        stem = when.strftime("%Y%m%d-%H%M%S")
        return sub / f"{stem}.{self._ext}"

    @property
    def base_dir(self) -> Path:
        return self._base
