"""Voice Activity Detection.

Gates raw PCM frames from :mod:`capture` into voice segments. The audio
worker uses this to emit ``voice.activity.started`` / ``voice.activity.ended``
events and to accumulate the PCM for STT.

Two backends:

* :class:`WebRTCVad` — official ``webrtcvad`` library (aggressive levels
  0–3). Preferred on RPi because of its CPU footprint and determinism.
* :class:`EnergyVad` — pure-Python RMS-threshold fallback used when
  ``webrtcvad`` is not installed. Good enough for manual testing on a dev
  machine; do not rely on it in quiet rooms with noisy backgrounds.

Both backends share :class:`VADSegmenter` which turns a per-frame ``True``/
``False`` stream into open/close transitions with hangover smoothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Iterator, Tuple

from .capture import FRAME_BYTES, FRAME_DURATION_MS, SAMPLE_RATE_HZ

_log = logging.getLogger(__name__)


class VADBackend:
    """Decides whether a single frame contains speech."""

    def is_speech(self, frame: bytes) -> bool:
        raise NotImplementedError


class EnergyVad(VADBackend):
    def __init__(self, rms_threshold: int = 500) -> None:
        self._thr = rms_threshold

    def is_speech(self, frame: bytes) -> bool:
        if len(frame) < 2:
            return False
        # cheap RMS without numpy
        acc = 0
        count = len(frame) // 2
        for i in range(0, len(frame), 2):
            lo = frame[i]
            hi = frame[i + 1]
            sample = lo | (hi << 8)
            if sample >= 0x8000:
                sample -= 0x10000
            acc += sample * sample
        rms = (acc / max(1, count)) ** 0.5
        return rms >= self._thr


class WebRTCVad(VADBackend):
    def __init__(self, aggressiveness: int = 2) -> None:
        try:
            import webrtcvad  # type: ignore
            self._vad = webrtcvad.Vad(aggressiveness)
        except Exception as e:  # pragma: no cover
            _log.info("webrtcvad unavailable (%s); install `webrtcvad`", e)
            raise

    def is_speech(self, frame: bytes) -> bool:
        try:
            return bool(self._vad.is_speech(frame, SAMPLE_RATE_HZ))
        except Exception:
            return False


def make_backend() -> VADBackend:
    try:
        return WebRTCVad()
    except Exception:
        return EnergyVad()


@dataclass
class VADSegmenter:
    """Turn a per-frame speech flag into start/end transitions.

    ``hangover_frames`` smooths out brief pauses (e.g., between words) so
    the VAD does not flap. ``onset_frames`` requires sustained speech
    before declaring the start, rejecting single-frame noise spikes.
    """
    backend: VADBackend
    onset_frames: int = 2
    hangover_frames: int = 10  # ~200 ms at 20 ms frames
    _consec_speech: int = 0
    _consec_silence: int = 0
    _in_voice: bool = False

    def push(self, frame: bytes) -> Tuple[bool, bool]:
        """Return ``(started, ended)`` flags for the frame boundary.

        Exactly one of the flags can be ``True`` on any given call; both are
        ``False`` when the state has not changed. The caller is responsible
        for buffering PCM and emitting the events.
        """
        is_speech = self.backend.is_speech(frame)
        if is_speech:
            self._consec_speech += 1
            self._consec_silence = 0
        else:
            self._consec_silence += 1
            self._consec_speech = 0

        started = False
        ended = False
        if not self._in_voice and self._consec_speech >= self.onset_frames:
            self._in_voice = True
            started = True
        elif self._in_voice and self._consec_silence >= self.hangover_frames:
            self._in_voice = False
            ended = True
        return started, ended

    @property
    def in_voice(self) -> bool:
        return self._in_voice


def segment(frames: Iterable[bytes], backend: VADBackend) -> Iterator[Tuple[bool, bool, bytes]]:
    """Convenience: yield ``(started, ended, frame)`` triples."""
    seg = VADSegmenter(backend=backend)
    for f in frames:
        started, ended = seg.push(f)
        yield started, ended, f
