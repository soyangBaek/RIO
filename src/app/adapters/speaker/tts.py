"""T-023: TTS 어댑터.

텍스트 → 음성 출력. 오프라인 TTS (pyttsx3) 또는 headless fallback.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class TtsAdapter:
    """Text-to-Speech 어댑터."""

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._engine = None
        self._lock = threading.Lock()

    def initialize(self) -> None:
        if self._headless:
            return
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 150)
            logger.info("TTS engine initialized")
        except (ImportError, Exception) as e:
            logger.warning("TTS fallback to headless: %s", e)
            self._headless = True

    def speak(self, text: str) -> None:
        """텍스트를 음성으로 출력."""
        if self._headless:
            logger.info("TTS (headless): %s", text)
            return

        with self._lock:
            try:
                if self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()
            except Exception as e:
                logger.warning("TTS speak error: %s", e)

    def speak_async(self, text: str) -> None:
        """비동기 TTS. 별도 스레드에서 실행."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()

    def shutdown(self) -> None:
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
