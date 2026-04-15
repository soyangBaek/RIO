from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CameraStream:
    device_index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 15
    frames: list[Any] | None = None
    _buffer: deque[Any] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.frames:
            self._buffer.extend(self.frames)

    def feed(self, frame: Any) -> None:
        self._buffer.append(frame)

    def read(self) -> Any:
        if self._buffer:
            return self._buffer.popleft()
        return {
            "device_index": self.device_index,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "mock": True,
        }
