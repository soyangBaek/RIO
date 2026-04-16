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
    use_camera: bool = False
    frames: list[Any] | None = None
    _buffer: deque[Any] = field(default_factory=deque)
    _capture: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.frames:
            self._buffer.extend(self.frames)

    def _ensure_capture(self) -> Any:
        if not self.use_camera:
            return None
        if self._capture is not None:
            return self._capture
        import cv2

        capture = cv2.VideoCapture(self.device_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
        capture.set(cv2.CAP_PROP_FPS, float(self.fps))
        if not capture.isOpened():
            raise RuntimeError(f"Unable to open camera device {self.device_index}")
        self._capture = capture
        return self._capture

    def feed(self, frame: Any) -> None:
        self._buffer.append(frame)

    def read(self) -> Any:
        if self._buffer:
            return self._buffer.popleft()
        if self.use_camera:
            capture = self._ensure_capture()
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Failed to read frame from camera")
            return frame
        return {
            "device_index": self.device_index,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "mock": True,
        }

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
