"""T-037: Voice Activity Detection (VAD).

오디오 스트림에서 음성 구간 탐지. webrtcvad 또는 에너지 기반 fallback.
"""
from __future__ import annotations

import logging
import struct
from typing import Optional

logger = logging.getLogger(__name__)

ENERGY_THRESHOLD = 500  # RMS energy threshold (fallback)


class VoiceActivityDetector:
    """VAD – 음성 구간 탐지."""

    def __init__(self, sensitivity: int = 2) -> None:
        """sensitivity: 0~3 (webrtcvad aggressiveness)."""
        self._sensitivity = sensitivity
        self._vad = None
        self._active = False
        self._silence_frames = 0
        self._max_silence_frames = 30  # ~1초 (30 * 30ms frame)
        self._init_vad()

    def _init_vad(self) -> None:
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(self._sensitivity)
            logger.info("WebRTC VAD initialized (mode=%d)", self._sensitivity)
        except ImportError:
            logger.warning("webrtcvad not available – using energy-based fallback")
            self._vad = None

    def process_chunk(self, audio_bytes: bytes, sample_rate: int = 16000) -> Optional[str]:
        """오디오 청크 처리.

        Returns:
            'started' – 음성 시작
            'ended'   – 음성 종료
            None      – 변화 없음
        """
        is_speech = self._detect_speech(audio_bytes, sample_rate)

        if is_speech:
            self._silence_frames = 0
            if not self._active:
                self._active = True
                return "started"
        else:
            if self._active:
                self._silence_frames += 1
                if self._silence_frames >= self._max_silence_frames:
                    self._active = False
                    self._silence_frames = 0
                    return "ended"
        return None

    def _detect_speech(self, audio_bytes: bytes, sample_rate: int) -> bool:
        if self._vad:
            try:
                # webrtcvad needs 10/20/30ms frames
                frame_duration = 30  # ms
                frame_size = int(sample_rate * frame_duration / 1000) * 2
                if len(audio_bytes) >= frame_size:
                    return self._vad.is_speech(audio_bytes[:frame_size], sample_rate)
            except Exception:
                pass

        # Energy-based fallback
        return self._energy_detect(audio_bytes)

    @staticmethod
    def _energy_detect(audio_bytes: bytes) -> bool:
        if len(audio_bytes) < 2:
            return False
        n_samples = len(audio_bytes) // 2
        samples = struct.unpack(f"<{n_samples}h", audio_bytes[:n_samples * 2])
        rms = (sum(s * s for s in samples) / n_samples) ** 0.5
        return rms > ENERGY_THRESHOLD

    @property
    def is_active(self) -> bool:
        return self._active
