from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(slots=True)
class TouchSample:
    x: int
    y: int
    timestamp: datetime


class TouchInputAdapter:
    """Small abstraction over touchscreen samples for tests and simulations."""

    def __init__(self, samples: Iterable[TouchSample] | None = None) -> None:
        self._samples = iter(samples or [])

    def read(self) -> TouchSample | None:
        return next(self._samples, None)

    @staticmethod
    def sample(x: int, y: int) -> TouchSample:
        return TouchSample(x=x, y=y, timestamp=datetime.now(timezone.utc))

