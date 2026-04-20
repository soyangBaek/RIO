"""RMS 기반 스트리밍 VAD: 16kHz float32 mono 청크를 받아 utterance 완성 시 반환."""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


@dataclass
class VADConfig:
    threshold: int
    min_silence_duration_ms: int
    speech_pad_ms: int
    min_speech_ms: int
    sample_rate: int = 16000


@dataclass
class UtteranceMeta:
    start_sample: int
    end_sample: int
    duration_ms: int
    passed_min_speech: bool
    peak: float
    rms: float


class RmsVAD:
    def __init__(self, cfg: VADConfig):
        self.cfg = cfg
        self.last_chunk_peak: float = 0.0
        self.last_chunk_rms: float = 0.0

        self._chunk_samples: int | None = None
        self._silence_chunks_to_end = 1
        self._speech_pad_chunks = 0
        self._sample_cursor = 0

        self._active = False
        self._silent_chunks = 0
        self._pre_roll: deque[tuple[int, np.ndarray]] = deque()
        self._current_chunks: list[tuple[int, np.ndarray]] = []
        self._pending_silence: list[tuple[int, np.ndarray]] = []

    def _ensure_geometry(self, chunk_samples: int) -> None:
        if self._chunk_samples == chunk_samples:
            return
        self._chunk_samples = chunk_samples
        chunk_ms = max(1.0, (chunk_samples / self.cfg.sample_rate) * 1000.0)
        self._silence_chunks_to_end = max(1, int(math.ceil(self.cfg.min_silence_duration_ms / chunk_ms)))
        self._speech_pad_chunks = max(0, int(math.ceil(self.cfg.speech_pad_ms / chunk_ms)))
        self._pre_roll = deque(maxlen=self._speech_pad_chunks or None)
        print(
            f"[{_ts()}] [vad] rms threshold={self.cfg.threshold} "
            f"silence_chunks={self._silence_chunks_to_end} pad_chunks={self._speech_pad_chunks}"
        )

    def process(self, chunk: np.ndarray) -> Optional[tuple[np.ndarray, UtteranceMeta]]:
        chunk = chunk.astype(np.float32, copy=False)
        self._ensure_geometry(len(chunk))

        chunk_start = self._sample_cursor
        chunk_end = chunk_start + len(chunk)
        self._sample_cursor = chunk_end

        self.last_chunk_peak = float(np.abs(chunk).max()) if len(chunk) else 0.0
        self.last_chunk_rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0
        rms_16bit = int(round(self.last_chunk_rms * 32768.0))
        voiced = rms_16bit >= self.cfg.threshold
        entry = (chunk_start, chunk.copy())

        if not self._active:
            if voiced:
                self._active = True
                self._silent_chunks = 0
                self._pending_silence = []
                self._current_chunks = list(self._pre_roll)
                self._current_chunks.append(entry)
                self._pre_roll.clear()
                start_sample = self._current_chunks[0][0]
                print(
                    f"[{_ts()}] [vad] speech START abs_sample={start_sample} "
                    f"chunk peak={self.last_chunk_peak:.3f} rms={self.last_chunk_rms:.3f}"
                )
                return None

            if self._speech_pad_chunks > 0:
                self._pre_roll.append(entry)
            return None

        if voiced:
            if self._pending_silence:
                self._current_chunks.extend(self._pending_silence)
                self._pending_silence = []
            self._silent_chunks = 0
            self._current_chunks.append(entry)
            return None

        self._pending_silence.append(entry)
        self._silent_chunks += 1
        if self._silent_chunks < self._silence_chunks_to_end:
            return None

        trailing = self._pending_silence[-self._speech_pad_chunks :] if self._speech_pad_chunks > 0 else []
        segments = self._current_chunks + trailing
        if not segments:
            self._reset_segment_state()
            return None

        audio = np.concatenate([part for _, part in segments]) if segments else np.zeros(0, dtype=np.float32)
        start_sample = segments[0][0]
        last_start, last_chunk = segments[-1]
        end_sample = last_start + len(last_chunk)
        duration_ms = int((end_sample - start_sample) / self.cfg.sample_rate * 1000)
        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
        passed = duration_ms >= self.cfg.min_speech_ms
        verdict = "-> ASR" if passed else f"-> DROP (< min_speech_ms={self.cfg.min_speech_ms})"
        print(
            f"[{_ts()}] [vad] speech END   dur={duration_ms}ms "
            f"peak={peak:.3f} rms={rms:.3f}  {verdict}"
        )

        meta = UtteranceMeta(
            start_sample=start_sample,
            end_sample=end_sample,
            duration_ms=duration_ms,
            passed_min_speech=passed,
            peak=peak,
            rms=rms,
        )
        self._reset_segment_state()
        return audio, meta

    def _reset_segment_state(self) -> None:
        self._active = False
        self._silent_chunks = 0
        self._current_chunks = []
        self._pending_silence = []
