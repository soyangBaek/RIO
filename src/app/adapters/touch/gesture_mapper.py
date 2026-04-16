"""Classify raw :class:`TouchPoint` samples into gesture events.

Samples are accumulated between press-down and release-up. On release the
buffered path is classified as either a ``tap`` or a ``stroke`` (petting
gesture) and an :class:`Event` is emitted on the bus. Anything else — short
drag, uncommitted touch — is ignored.

Scenarios covered:
- ``INT-03a/b/c`` — tap with varying Context
- ``INT-04`` — petting stroke triggers happy oneshot
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ...core.events import topics
from ...core.events.models import Event
from .input import TouchPoint

Publisher = Callable[[Event], None]


@dataclass(frozen=True)
class GestureParams:
    tap_max_duration_ms: int = 300
    tap_max_path: float = 0.02          # normalized
    stroke_min_path: float = 0.08        # normalized
    stroke_min_samples: int = 3


@dataclass
class _Stroke:
    start_ts: float
    samples: List[TouchPoint] = field(default_factory=list)


class TouchGestureMapper:
    def __init__(
        self,
        publish: Publisher,
        params: GestureParams = GestureParams(),
    ) -> None:
        self._publish = publish
        self._params = params
        self._active: Optional[_Stroke] = None

    def on_sample(self, point: TouchPoint) -> None:
        if point.pressed:
            if self._active is None:
                self._active = _Stroke(start_ts=point.timestamp)
            self._active.samples.append(point)
            return

        # release (pressed=False)
        if self._active is None:
            return
        stroke = self._active
        self._active = None
        if not stroke.samples:
            return

        duration_ms = (point.timestamp - stroke.start_ts) * 1000.0
        path_len = _path_length(stroke.samples)

        if (
            duration_ms <= self._params.tap_max_duration_ms
            and path_len <= self._params.tap_max_path
        ):
            last = stroke.samples[-1]
            self._publish(
                Event(
                    topic=topics.TOUCH_TAP_DETECTED,
                    payload={"x": last.x, "y": last.y},
                    timestamp=point.timestamp,
                    source="touch",
                )
            )
            return

        if (
            path_len >= self._params.stroke_min_path
            and len(stroke.samples) >= self._params.stroke_min_samples
        ):
            path = [(p.x, p.y) for p in stroke.samples]
            self._publish(
                Event(
                    topic=topics.TOUCH_STROKE_DETECTED,
                    payload={"path": path, "duration": duration_ms / 1000.0},
                    timestamp=point.timestamp,
                    source="touch",
                )
            )


def _path_length(samples: List[TouchPoint]) -> float:
    total = 0.0
    for a, b in zip(samples, samples[1:]):
        total += math.hypot(b.x - a.x, b.y - a.y)
    return total
