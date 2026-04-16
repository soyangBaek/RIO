"""Vision capture — BGR frame stream from the RPi webcam.

Uses OpenCV's ``VideoCapture`` (V4L2 on Linux) when available, otherwise
falls back to :class:`NullCamera` which yields empty frames on a slow
cadence. The vision worker consumes the frames, feeds the face detector
and gesture detector, and publishes ``vision.*`` events.

Resolution/fps are picked from ``configs/robot.yaml``.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Iterator, Optional

_log = logging.getLogger(__name__)


class NullCamera:
    def __init__(self, fps: int = 15) -> None:
        self._interval = 1.0 / max(1, fps)
        self._stop = threading.Event()

    def frames(self) -> Iterator[Optional[object]]:
        """Yield ``None`` placeholders at the configured cadence."""
        while not self._stop.is_set():
            yield None
            time.sleep(self._interval)

    def stop(self) -> None:
        self._stop.set()


class CV2Camera:
    def __init__(
        self,
        device: int = 0,
        width_px: int = 640,
        height_px: int = 480,
        fps: int = 15,
    ) -> None:
        self._stop = threading.Event()
        self._cap = None
        try:
            import cv2  # type: ignore
            cap = cv2.VideoCapture(device)
            if not cap.isOpened():
                _log.info("cv2 VideoCapture could not open device %s", device)
                cap.release()
                self._cap = None
            else:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width_px)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height_px)
                cap.set(cv2.CAP_PROP_FPS, fps)
                self._cap = cap
        except Exception as e:  # pragma: no cover - hardware dependent
            _log.warning("opencv unavailable (%s); camera disabled", e)
            self._cap = None
        self._interval = 1.0 / max(1, fps)

    def frames(self) -> Iterator[Optional[object]]:
        while not self._stop.is_set():
            if self._cap is None:
                yield None
                time.sleep(self._interval)
                continue
            ok, frame = self._cap.read()
            if not ok:
                yield None
            else:
                yield frame

    def stop(self) -> None:
        self._stop.set()
        if self._cap is not None:  # pragma: no cover
            try:
                self._cap.release()
            except Exception:
                pass


def make_camera(**kwargs):
    try:
        cam = CV2Camera(**kwargs)
        if cam._cap is not None:
            return cam
    except Exception:  # pragma: no cover
        pass
    return NullCamera()
