"""Microphone capture — PCM frames at 16 kHz mono.

Used exclusively by :mod:`workers.audio_worker`. The worker subscribes its
VAD and STT to the frame iterator. Two backends are offered:

* :class:`SoundDeviceCapture` — via the ``sounddevice`` package (PortAudio).
  Handles most Linux/RPi setups. Selected via ``configs/robot.yaml``.
* :class:`NullCapture` — yields empty bytes forever on a slow cadence; used
  on dev hosts without a mic.

Both backends return a generator of ``bytes`` frames (16-bit signed
little-endian PCM, mono). Downstream VAD/STT operate on this format.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Iterator, Optional

_log = logging.getLogger(__name__)

SAMPLE_RATE_HZ = 16_000
FRAME_DURATION_MS = 20
FRAME_SAMPLES = SAMPLE_RATE_HZ * FRAME_DURATION_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2  # int16


class NullCapture:
    def __init__(self) -> None:
        self._stop = threading.Event()

    def frames(self) -> Iterator[bytes]:
        interval = FRAME_DURATION_MS / 1000.0
        silence = b"\x00" * FRAME_BYTES
        while not self._stop.is_set():
            yield silence
            time.sleep(interval)

    def stop(self) -> None:
        self._stop.set()


class SoundDeviceCapture:
    def __init__(self, device: Optional[int] = None) -> None:
        self._device = device
        self._stop = threading.Event()
        self._queue: list[bytes] = []
        self._condition = threading.Condition()
        self._stream = None
        try:
            import sounddevice as sd  # type: ignore

            def _cb(indata, frames, time_info, status) -> None:  # type: ignore
                if status:
                    _log.warning("sounddevice status: %s", status)
                pcm = bytes(indata)
                with self._condition:
                    self._queue.append(pcm)
                    self._condition.notify()

            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE_HZ,
                blocksize=FRAME_SAMPLES,
                dtype="int16",
                channels=1,
                callback=_cb,
                device=device,
            )
            self._stream.start()
        except Exception as e:  # pragma: no cover - hardware dependent
            _log.warning("sounddevice unavailable (%s); mic capture disabled", e)
            self._stream = None

    def frames(self) -> Iterator[bytes]:
        while not self._stop.is_set():
            if self._stream is None:
                # graceful degradation: yield silence at cadence
                time.sleep(FRAME_DURATION_MS / 1000.0)
                yield b"\x00" * FRAME_BYTES
                continue
            with self._condition:
                if not self._queue:
                    self._condition.wait(timeout=0.2)
                chunk = bytes().join(self._queue) if self._queue else None
                self._queue.clear()
            if chunk:
                yield chunk

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:  # pragma: no cover
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass


def make_capture(device: Optional[int] = None):
    try:
        cap = SoundDeviceCapture(device=device)
        if cap._stream is not None:
            return cap
    except Exception:  # pragma: no cover
        pass
    return NullCapture()
