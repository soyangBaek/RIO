"""Single-frame webcam snapshot.

Called by :class:`PhotoService` at the shutter point. Uses OpenCV (``cv2``)
to open the camera, grab a frame, and write it through
:class:`PhotoStorage`. The module is deliberately synchronous: the photo
service already runs the shutter on its own timer thread.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .storage import PhotoStorage

_log = logging.getLogger(__name__)


class CameraSnapshot:
    def __init__(self, storage: PhotoStorage, device: int = 0) -> None:
        self._storage = storage
        self._device = device

    def capture(self) -> Optional[Path]:
        try:
            import cv2  # type: ignore
        except ImportError:
            _log.info("opencv not installed; snapshot disabled")
            return None

        cap = cv2.VideoCapture(self._device)
        try:
            if not cap.isOpened():
                _log.warning("cannot open camera %s for snapshot", self._device)
                return None
            # Warm-up frame — first read from V4L2 can be black.
            cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                return None
            path = self._storage.new_path()
            if not cv2.imwrite(str(path), frame):
                _log.warning("cv2.imwrite failed for %s", path)
                return None
            return path
        finally:
            try:
                cap.release()
            except Exception:
                pass
