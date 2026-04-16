"""T-044: 사진 저장소 관리.

저장 경로 생성, 파일명 규칙, 용량 관리.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PHOTO_DIR = "photos"
MAX_PHOTOS = 1000


class PhotoStorage:
    """사진 파일 저장소."""

    def __init__(self, base_dir: str = DEFAULT_PHOTO_DIR) -> None:
        self._base = Path(base_dir)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self._base.mkdir(parents=True, exist_ok=True)

    def generate_path(self, prefix: str = "rio") -> str:
        """새 사진 파일 경로 생성."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{ts}.jpg"
        return str(self._base / filename)

    def save_frame(self, frame, file_path: Optional[str] = None) -> str:
        """프레임을 파일로 저장. 경로 반환."""
        if file_path is None:
            file_path = self.generate_path()

        try:
            import cv2
            cv2.imwrite(file_path, frame)
            logger.info("Photo saved: %s", file_path)
        except ImportError:
            # dummy save
            Path(file_path).touch()
            logger.info("Photo saved (dummy): %s", file_path)

        self._cleanup_if_needed()
        return file_path

    def _cleanup_if_needed(self) -> None:
        """MAX_PHOTOS 초과 시 가장 오래된 파일 삭제."""
        try:
            files = sorted(self._base.glob("*.jpg"), key=lambda f: f.stat().st_mtime)
            while len(files) > MAX_PHOTOS:
                oldest = files.pop(0)
                oldest.unlink()
                logger.debug("Cleaned up old photo: %s", oldest)
        except Exception:
            pass

    @property
    def photo_count(self) -> int:
        return len(list(self._base.glob("*.jpg")))

    @property
    def base_dir(self) -> str:
        return str(self._base)
