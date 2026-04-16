"""T-036: 마이크 캡처 어댑터.

PyAudio 기반 오디오 스트림. headless fallback.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

RATE = 16000
CHUNK = 1024
FORMAT_WIDTH = 2  # 16-bit


class AudioCapture:
    """마이크 입력 캡처."""

    def __init__(self, device_index: Optional[int] = None, headless: bool = False) -> None:
        self._device_index = device_index
        self._headless = headless
        self._stream = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, on_chunk: Callable[[bytes], None]) -> None:
        """캡처 시작. on_chunk(audio_bytes) 콜백으로 청크 전달."""
        if self._headless:
            logger.info("AudioCapture: headless mode")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, args=(on_chunk,), daemon=True
        )
        self._thread.start()

    def _capture_loop(self, on_chunk: Callable[[bytes], None]) -> None:
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            self._stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=RATE,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=CHUNK,
            )
            logger.info("AudioCapture started")
            while self._running:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                on_chunk(data)
        except ImportError:
            logger.warning("pyaudio not available")
        except Exception as e:
            logger.error("AudioCapture error: %s", e)
        finally:
            self._cleanup()

    def stop(self) -> None:
        self._running = False

    def _cleanup(self) -> None:
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
