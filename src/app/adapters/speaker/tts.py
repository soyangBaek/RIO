"""Text-to-speech output.

Exposes a small :class:`TTS` interface and two implementations:

* :class:`PyTtsx3TTS` — uses ``pyttsx3`` (offline, cross-platform) if the
  package is importable. Calls run on a background thread so ``speak``
  never blocks the main loop.
* :class:`NullTTS` — no-op backend used on dev hosts without audio or when
  the mic/speaker capability is degraded.

Higher-level scenes (weather briefing, timer ack, error narration) call
:meth:`speak` with the final text. Language selection is delegated to
``configs/robot.yaml``.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional, Protocol

_log = logging.getLogger(__name__)


class TTS(Protocol):
    def speak(self, text: str, priority: int = 0) -> None: ...
    def stop(self) -> None: ...


class NullTTS:
    def speak(self, text: str, priority: int = 0) -> None:
        _log.info("NullTTS(speak): %s", text)

    def stop(self) -> None:
        pass


class PyTtsx3TTS:
    """Offline TTS via pyttsx3. Safe to instantiate when pyttsx3 is absent —
    it falls back to :class:`NullTTS` behaviour and logs once."""

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        language: Optional[str] = None,
    ) -> None:
        self._engine = None
        try:
            import pyttsx3  # type: ignore
            self._engine = pyttsx3.init()
            if voice:
                self._engine.setProperty("voice", voice)
            if rate:
                self._engine.setProperty("rate", rate)
            self._language = language
        except Exception as e:  # pragma: no cover - hardware dependent
            _log.warning("pyttsx3 unavailable (%s); TTS disabled", e)
            self._engine = None
            self._language = None

        self._queue: "queue.PriorityQueue[tuple[int,int,str]]" = queue.PriorityQueue()
        self._stop = threading.Event()
        self._seq = 0
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="tts-worker"
        )
        self._thread.start()

    def speak(self, text: str, priority: int = 0) -> None:
        if not text:
            return
        # lower value = higher priority (PriorityQueue is a min-heap)
        self._seq += 1
        self._queue.put((-priority, self._seq, text))

    def stop(self) -> None:
        self._stop.set()
        # unblock worker
        self._queue.put((0, self._seq + 1, ""))
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                _, _, text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if not text or self._engine is None:
                continue
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception:
                _log.exception("tts runAndWait failed")
