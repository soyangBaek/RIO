"""Silero VAD 스트리밍 래퍼: 16kHz/512샘플 청크를 받아 utterance 완성 시 (audio, meta) 반환."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


@dataclass
class VADConfig:
    threshold: float
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
    peak: float  # 발화 구간 float32 |amplitude| 최대 (0.0~1.0 이론치)
    rms: float   # 발화 구간 float32 RMS


# Silero VAD ONNX 는 16kHz에서 정확히 512 샘플 청크를 요구.
EXPECTED_CHUNK_16K = 512


class _AudioBuffer:
    """absolute sample index 로 접근 가능한 롤링 버퍼."""

    def __init__(self, max_seconds: float, sample_rate: int):
        self.max_samples = int(max_seconds * sample_rate)
        self.samples = np.zeros(0, dtype=np.float32)
        self.start_idx = 0  # samples[0] 의 absolute index

    def push(self, chunk: np.ndarray) -> None:
        self.samples = np.concatenate([self.samples, chunk])
        if len(self.samples) > self.max_samples:
            drop = len(self.samples) - self.max_samples
            self.samples = self.samples[drop:]
            self.start_idx += drop

    def extract(self, abs_start: int, abs_end: int) -> np.ndarray:
        rel_start = max(0, abs_start - self.start_idx)
        rel_end = max(rel_start, abs_end - self.start_idx)
        return self.samples[rel_start:rel_end].copy()


class SileroVAD:
    def __init__(self, cfg: VADConfig):
        self.cfg = cfg
        print(f"[vad] loading silero-vad (threshold={cfg.threshold}, "
              f"min_silence={cfg.min_silence_duration_ms}ms, pad={cfg.speech_pad_ms}ms)")
        self.model = load_silero_vad(onnx=True)
        self.iter = VADIterator(
            self.model,
            threshold=cfg.threshold,
            sampling_rate=cfg.sample_rate,
            min_silence_duration_ms=cfg.min_silence_duration_ms,
            speech_pad_ms=cfg.speech_pad_ms,
        )
        self._buf = _AudioBuffer(max_seconds=30.0, sample_rate=cfg.sample_rate)
        self._seg_start: Optional[int] = None
        # 콜백 대비 최근 청크 레벨 (heartbeat/디버그용).
        self.last_chunk_peak: float = 0.0
        self.last_chunk_rms: float = 0.0

    def process(self, chunk: np.ndarray) -> Optional[tuple[np.ndarray, UtteranceMeta]]:
        """청크 하나를 VAD 에 공급. utterance 끝이 감지되면 (audio, meta) 반환."""
        if len(chunk) != EXPECTED_CHUNK_16K and self.cfg.sample_rate == 16000:
            # silero-vad 는 정확히 512 샘플(16kHz) 혹은 256 샘플(8kHz)만 허용.
            # blocksize 를 config.yaml 에서 맞춰줘야 함.
            raise ValueError(
                f"Silero VAD expects {EXPECTED_CHUNK_16K} samples per chunk at "
                f"{self.cfg.sample_rate}Hz, got {len(chunk)}. "
                f"Check audio.blocksize in config.yaml."
            )

        self._buf.push(chunk)

        # 청크 레벨 스냅샷 (heartbeat 에서 사용).
        self.last_chunk_peak = float(np.abs(chunk).max()) if len(chunk) else 0.0
        self.last_chunk_rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0

        tensor = torch.from_numpy(chunk.astype(np.float32))
        event = self.iter(tensor, return_seconds=False)

        if event is None:
            return None

        if "start" in event:
            self._seg_start = int(event["start"])
            print(f"[{_ts()}] [vad] speech START  abs_sample={self._seg_start} "
                  f"chunk peak={self.last_chunk_peak:.3f} rms={self.last_chunk_rms:.3f}")
            return None

        if "end" in event:
            end_sample = int(event["end"])
            start_sample = self._seg_start if self._seg_start is not None else 0
            self._seg_start = None
            duration_ms = int((end_sample - start_sample) / self.cfg.sample_rate * 1000)
            audio = self._buf.extract(start_sample, end_sample)

            peak = float(np.abs(audio).max()) if len(audio) else 0.0
            rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
            passed = duration_ms >= self.cfg.min_speech_ms
            verdict = "→ ASR" if passed else f"→ DROP (< min_speech_ms={self.cfg.min_speech_ms})"
            print(f"[{_ts()}] [vad] speech END    dur={duration_ms}ms "
                  f"peak={peak:.3f} rms={rms:.3f}  {verdict}")

            meta = UtteranceMeta(
                start_sample=start_sample,
                end_sample=end_sample,
                duration_ms=duration_ms,
                passed_min_speech=passed,
                peak=peak,
                rms=rms,
            )
            return audio, meta

        return None
