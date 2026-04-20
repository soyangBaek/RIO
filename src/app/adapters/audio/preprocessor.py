"""오디오 전처리 유틸리티.

마이크에서 캡처한 오디오에 노이즈 게이트 / 정규화 / 고주파 필터를 적용하여
STT 모델의 입력 품질을 높인다.
"""

from __future__ import annotations

import numpy as np


def normalize_volume(audio: np.ndarray, target_rms: float = 0.1) -> np.ndarray:
    """RMS 기반 볼륨 정규화. 너무 작거나 큰 입력을 일정 레벨로 맞춘다."""
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
    if rms < 1e-6:
        return audio
    gain = target_rms / rms
    gain = min(gain, 10.0)  # 과도한 증폭 방지
    return np.clip(audio * gain, -1.0, 1.0).astype(audio.dtype)


def noise_gate(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """간단한 노이즈 게이트. threshold 이하의 신호를 0으로 만든다."""
    mask = np.abs(audio) > threshold
    return audio * mask


def highpass_filter(audio: np.ndarray, cutoff_ratio: float = 0.01) -> np.ndarray:
    """1차 IIR 하이패스 필터. 저주파 험/바람 소음을 제거한다.

    cutoff_ratio ≈ cutoff_freq / sample_rate. 16kHz에서 0.01 → ~160Hz 이하 제거.
    """
    alpha = 1.0 / (1.0 + cutoff_ratio * 2 * np.pi)
    out = np.zeros_like(audio, dtype=np.float64)
    prev_in = 0.0
    prev_out = 0.0
    for i in range(len(audio)):
        out[i] = alpha * (prev_out + audio[i] - prev_in)
        prev_in = audio[i]
        prev_out = out[i]
    return out.astype(audio.dtype)


def preprocess_audio(
    audio: np.ndarray,
    *,
    sample_rate: int = 16000,
    apply_highpass: bool = True,
    apply_gate: bool = True,
    apply_normalize: bool = True,
    gate_threshold: float = 0.01,
    highpass_cutoff: float = 0.01,
    target_rms: float = 0.1,
) -> np.ndarray:
    """전처리 파이프라인: 하이패스 → 노이즈 게이트 → 볼륨 정규화."""
    result = audio.astype(np.float32)
    if apply_highpass:
        result = highpass_filter(result, cutoff_ratio=highpass_cutoff)
    if apply_gate:
        result = noise_gate(result, threshold=gate_threshold)
    if apply_normalize:
        result = normalize_volume(result, target_rms=target_rms)
    return result
