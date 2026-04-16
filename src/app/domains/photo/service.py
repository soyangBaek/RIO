"""T-032: Photo service – 사진 촬영 시퀀스.

countdown → shutter → save → feedback.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

COUNTDOWN_SECONDS = 3


class PhotoService:
    """사진 촬영 도메인 서비스."""

    def __init__(self, camera_capture: Any = None, sfx_player: Any = None) -> None:
        self._camera = camera_capture
        self._sfx = sfx_player

    def handle(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        """executor_registry에서 호출되는 핸들러.

        별도 스레드에서 countdown + capture 실행.
        """
        t = threading.Thread(
            target=self._execute, args=(payload, done_callback), daemon=True
        )
        t.start()

    def _execute(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        try:
            # countdown
            for i in range(COUNTDOWN_SECONDS, 0, -1):
                logger.info("Photo countdown: %d", i)
                time.sleep(1)

            # shutter sound
            if self._sfx:
                self._sfx.play("shutter")

            # capture
            file_path = None
            if self._camera:
                file_path = self._camera.capture_photo()
            else:
                file_path = f"photos/rio_photo_{int(time.time())}.jpg"
                logger.info("Photo captured (dummy): %s", file_path)

            done_callback(True, result={"file_path": file_path})

        except Exception as e:
            logger.exception("Photo capture error")
            done_callback(False, error=str(e))
