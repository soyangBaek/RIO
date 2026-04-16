"""Speech-to-text adapter.

Baseline engine: **faster-whisper** with the ``tiny.en`` model, as pinned
in the T-038 task description. The choice is driven by latency on a
Raspberry Pi 4 (≈0.3 s end-to-end for a short utterance) and the fact that
no external network call is required.

Other backends can be swapped in by implementing :class:`STTBackend`; the
audio worker holds the interface rather than the concrete class.

Scenarios:

- Confidence below ``stt_confidence_min`` (see ``configs/thresholds.yaml``)
  causes the audio worker to emit ``voice.intent.unknown`` (VOICE-02).
- Complete backend failure (import error, model load error, inference
  exception) causes :func:`make_backend` to return :class:`NullSTT`, which
  always yields ``("", 0.0)``. The worker treats this as a degraded audio
  pipeline and publishes ``system.degraded.entered`` with
  ``lost_capability=voice`` (OPS-05b).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

_log = logging.getLogger(__name__)


class STTBackend(Protocol):
    def transcribe(self, pcm: bytes) -> Tuple[str, float]:
        """Return ``(text, confidence)``; empty ``text`` means no speech."""
        ...


class NullSTT:
    def transcribe(self, pcm: bytes) -> Tuple[str, float]:
        return ("", 0.0)


@dataclass
class FasterWhisperSTT:
    """``faster-whisper`` STT — pinned to ``tiny.en`` by default.

    Language is fixed to English unless overridden via ``language`` (e.g.
    ``"ko"`` for Korean); the default is chosen for speed on RPi. For Korean
    deployments, set ``model_size="small"`` and ``language="ko"`` via
    ``configs/robot.yaml``.
    """
    model_size: str = "tiny.en"
    language: Optional[str] = None  # None = auto-detect (slower)
    sample_rate_hz: int = 16_000
    device: str = "cpu"
    compute_type: str = "int8"

    def __post_init__(self) -> None:
        self._model = None
        try:
            from faster_whisper import WhisperModel  # type: ignore
            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        except Exception as e:  # pragma: no cover - env dependent
            _log.warning("faster-whisper unavailable (%s); STT disabled", e)
            self._model = None

    def transcribe(self, pcm: bytes) -> Tuple[str, float]:
        if self._model is None or not pcm:
            return ("", 0.0)
        try:
            import numpy as np  # type: ignore
            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            segments, info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=1,
                vad_filter=False,
            )
            parts: list[str] = []
            prob_sum = 0.0
            prob_count = 0
            for s in segments:
                parts.append(s.text)
                # ``avg_logprob`` in [-inf, 0]; map to confidence in [0, 1].
                lp = getattr(s, "avg_logprob", 0.0)
                if lp is not None:
                    import math
                    prob_sum += math.exp(lp)
                    prob_count += 1
            text = "".join(parts).strip()
            confidence = (prob_sum / prob_count) if prob_count else 0.0
            return (text, min(1.0, max(0.0, confidence)))
        except Exception:
            _log.exception("faster-whisper transcribe failed")
            return ("", 0.0)


def make_backend(**kwargs) -> STTBackend:
    """Attempt FasterWhisperSTT; fall back to NullSTT on failure."""
    try:
        fw = FasterWhisperSTT(**kwargs)
        if fw._model is not None:
            return fw
    except Exception:  # pragma: no cover
        pass
    return NullSTT()
