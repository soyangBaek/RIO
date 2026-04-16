"""T-038: STT (Speech-to-Text) 어댑터.

Whisper (로컬) 또는 Google STT. headless fallback.
"""
from __future__ import annotations

import logging
import tempfile
import wave
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SttAdapter:
    """음성 → 텍스트 변환."""

    def __init__(self, engine: str = "whisper", model_size: str = "base", headless: bool = False) -> None:
        self._engine = engine
        self._model_size = model_size
        self._headless = headless
        self._model = None

    def initialize(self) -> None:
        if self._headless:
            return

        if self._engine == "whisper":
            try:
                import whisper
                self._model = whisper.load_model(self._model_size)
                logger.info("Whisper model loaded: %s", self._model_size)
            except ImportError:
                logger.warning("whisper not available – STT disabled")
                self._headless = True
        else:
            logger.info("STT engine: %s (not implemented, headless)", self._engine)
            self._headless = True

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
        """오디오 바이트 → (텍스트, confidence).

        Returns: (text, confidence)
        """
        if self._headless or self._model is None:
            return "", 0.0

        try:
            # whisper는 파일 기반 → temp 파일 생성
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                with wave.open(tmp.name, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_bytes)

                result = self._model.transcribe(tmp.name, language="ko")
                text = result.get("text", "").strip()
                # whisper는 segment-level confidence 제공
                segments = result.get("segments", [])
                if segments:
                    avg_conf = sum(s.get("no_speech_prob", 0.5) for s in segments) / len(segments)
                    confidence = 1.0 - avg_conf
                else:
                    confidence = 0.5

                return text, confidence

        except Exception as e:
            logger.error("STT error: %s", e)
            return "", 0.0

    def transcribe_file(self, file_path: str) -> Tuple[str, float]:
        """파일 기반 변환."""
        if self._headless or self._model is None:
            return "", 0.0

        try:
            result = self._model.transcribe(file_path, language="ko")
            text = result.get("text", "").strip()
            return text, 0.8
        except Exception as e:
            logger.error("STT file error: %s", e)
            return "", 0.0
