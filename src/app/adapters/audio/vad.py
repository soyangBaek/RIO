from __future__ import annotations

import audioop
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class VoiceActivityDetector:
    threshold: int = 400
    silence_frames_to_end: int = 2
    _active: bool = field(default=False, init=False, repr=False)
    _silence_count: int = field(default=0, init=False, repr=False)

    def _is_speech(self, frame: Any) -> bool:
        if frame is None:
            return False
        if isinstance(frame, dict):
            if "speech" in frame:
                return bool(frame["speech"])
            pcm = frame.get("pcm")
            if isinstance(pcm, (bytes, bytearray)):
                return self._is_speech(pcm)
            return bool(frame.get("transcript"))
        if isinstance(frame, (bytes, bytearray)) and len(frame) >= 2:
            try:
                return audioop.rms(frame, 2) >= self.threshold
            except audioop.error:
                return bool(frame)
        return bool(frame)

    def process(self, frame: Any, *, now: datetime | None = None) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        is_speech = self._is_speech(frame)
        events: list[Event] = []

        if is_speech and not self._active:
            self._active = True
            self._silence_count = 0
            events.append(Event.create(topics.VOICE_ACTIVITY_STARTED, "audio.vad", timestamp=when))
        elif is_speech:
            self._silence_count = 0
        elif self._active:
            self._silence_count += 1
            if self._silence_count >= self.silence_frames_to_end:
                self._active = False
                self._silence_count = 0
                events.append(Event.create(topics.VOICE_ACTIVITY_ENDED, "audio.vad", timestamp=when))
        return events
