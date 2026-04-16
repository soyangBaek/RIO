"""T-045: 카메라 캡처 어댑터 – 사진 촬영용.

vision worker의 camera_stream 과 별도. photo service에서 단발 촬영.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.app.adapters.camera.storage import PhotoStorage

logger = logging.getLogger(__name__)


class CameraCapture:
    """사진 촬영 전용 카메라 어댑터."""

    def __init__(
        self,
        device_index: int = 0,
        storage: Optional[PhotoStorage] = None,
        headless: bool = False,
    ) -> None:
        self._device_index = device_index
        self._storage = storage or PhotoStorage()
        self._headless = headless

    def capture_photo(self, file_path: Optional[str] = None) -> str:
        """사진 1장 촬영 → 저장 경로 반환."""
        if file_path is None:
            file_path = self._storage.generate_path()

        if self._headless:
            from pathlib import Path
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            Path(file_path).touch()
            logger.info("Photo captured (headless dummy): %s", file_path)
            return file_path

        try:
            import cv2
            cap = cv2.VideoCapture(self._device_index)
            if not cap.isOpened():
                logger.error("Camera not available for capture")
                # dummy fallback
                from pathlib import Path
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                Path(file_path).touch()
                return file_path

            ret, frame = cap.read()
            cap.release()

            if ret:
                return self._storage.save_frame(frame, file_path)
            else:
                logger.error("Failed to read frame for capture")
                from pathlib import Path
                Path(file_path).touch()
                return file_path

        except ImportError:
            from pathlib import Path
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            Path(file_path).touch()
            logger.info("Photo captured (no cv2, dummy): %s", file_path)
            return file_path
