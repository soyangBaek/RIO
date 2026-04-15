from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class PhotoStorage:
    root_dir: Path = Path("data/photos")

    def ensure_daily_dir(self, *, now: datetime | None = None) -> Path:
        when = now or datetime.now(timezone.utc)
        day_dir = self.root_dir / when.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def next_photo_path(self, *, now: datetime | None = None) -> Path:
        when = now or datetime.now(timezone.utc)
        day_dir = self.ensure_daily_dir(now=when)
        return day_dir / f"rio_{when.strftime('%H%M%S_%f')}.jpg"
