"""faster-whisper 래퍼: numpy float32 16kHz 오디오를 받아 텍스트 + 디버그 메트릭 반환."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel


@dataclass
class ASRConfig:
    model: str
    language: str
    beam_size: int
    compute_type: str
    device: str
    no_speech_threshold: float
    condition_on_previous_text: bool


@dataclass
class ASRResult:
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    decode_ms: int
    language: str


class WhisperASR:
    def __init__(self, cfg: ASRConfig):
        self.cfg = cfg
        print(f"[asr] loading faster-whisper '{cfg.model}' "
              f"(compute_type={cfg.compute_type}, device={cfg.device})...")
        self.model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)
        print("[asr] model ready")

    def transcribe(self, audio_16k_float32: np.ndarray) -> ASRResult:
        t0 = time.perf_counter()
        segments, info = self.model.transcribe(
            audio_16k_float32,
            language=self.cfg.language,
            beam_size=self.cfg.beam_size,
            no_speech_threshold=self.cfg.no_speech_threshold,
            condition_on_previous_text=self.cfg.condition_on_previous_text,
        )
        segs = list(segments)
        decode_ms = int((time.perf_counter() - t0) * 1000)

        detected_lang = info.language if info is not None else self.cfg.language

        if not segs:
            return ASRResult(
                text="",
                avg_logprob=-float("inf"),
                no_speech_prob=1.0,
                compression_ratio=0.0,
                decode_ms=decode_ms,
                language=detected_lang,
            )

        text = " ".join(s.text.strip() for s in segs).strip()
        n = len(segs)
        return ASRResult(
            text=text,
            avg_logprob=sum(s.avg_logprob for s in segs) / n,
            no_speech_prob=sum(s.no_speech_prob for s in segs) / n,
            compression_ratio=sum(s.compression_ratio for s in segs) / n,
            decode_ms=decode_ms,
            language=detected_lang,
        )
