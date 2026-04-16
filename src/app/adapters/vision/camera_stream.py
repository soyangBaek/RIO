"""T-040: 카메라 프레임 수신.

OpenCV VideoCapture 기반. headless fallback.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CameraStream:
    """카메라 프레임 스트림."""

    def __init__(self, device_index: int = 0, headless: bool = False) -> None:
        self._device_index = device_index
        self._headless = headless
        self._cap = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_width = 640
        self._frame_height = 480

    def start(self, on_frame: Callable[[Any], None]) -> None:
        """프레임 캡처 시작. on_frame(numpy_array) 콜백."""
        if self._headless:
            logger.info("CameraStream: headless mode")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, args=(on_frame,), daemon=True
        )
        self._thread.start()

    def _capture_loop(self, on_frame: Callable) -> None:
        try:
            import cv2
            self._cap = cv2.VideoCapture(self._device_index)
            if not self._cap.isOpened():
                logger.error("Camera device %d not available", self._device_index)
                return

            self._frame_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._frame_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info("CameraStream started: %dx%d", self._frame_width, self._frame_height)

            while self._running:
                ret, frame = self._cap.read()
                if ret:
                    on_frame(frame)
                else:
                    time.sleep(0.01)

        except ImportError:
            logger.warning("OpenCV not available")
        except Exception as e:
            logger.error("CameraStream error: %s", e)
        finally:
            self._cleanup()

    def read_frame(self) -> Optional[Any]:
        """단일 프레임 읽기 (동기)."""
        if self._headless or self._cap is None:
            return None
        try:
            ret, frame = self._cap.read()
            return frame if ret else None
        except Exception:
            return None

    def stop(self) -> None:
        self._running = False

    def _cleanup(self) -> None:
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    @property
    def resolution(self) -> tuple:
        return (self._frame_width, self._frame_height)
