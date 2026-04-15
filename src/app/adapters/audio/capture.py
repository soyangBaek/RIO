from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AudioCapture:
    sample_rate: int = 16_000
    chunk_size: int = 1_600
    frames: list[Any] | None = None
    _buffer: deque[Any] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.frames:
            self._buffer.extend(self.frames)

    def feed(self, frame: Any) -> None:
        self._buffer.append(frame)

    def read_chunk(self) -> Any | None:
        if self._buffer:
            return self._buffer.popleft()
        return None

    def close(self) -> None:
        self._buffer.clear()
