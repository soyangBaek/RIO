from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass(slots=True)
class AudioCapture:
    sample_rate: int = 16_000
    chunk_size: int = 1_600
    frames: list[Any] | None = None
    _buffer: deque[Any] = field(default_factory=deque)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.frames:
            self._buffer.extend(self.frames)

    def feed(self, frame: Any) -> None:
        with self._lock:
            self._buffer.append(frame)

    def read_chunk(self) -> Any | None:
        with self._lock:
            if self._buffer:
                return self._buffer.popleft()
            return None

    def drain_chunks(self, *, max_items: int | None = None) -> list[Any]:
        frames: list[Any] = []
        with self._lock:
            while self._buffer and (max_items is None or len(frames) < max_items):
                frames.append(self._buffer.popleft())
        return frames

    def pending_count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def close(self) -> None:
        with self._lock:
            self._buffer.clear()
