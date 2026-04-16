from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.core.events import topics
from src.app.core.events.models import Event


@dataclass(slots=True)
class TerminalVoiceInput:
    normalizer: IntentNormalizer

    def build_events(
        self,
        transcript: str,
        *,
        confidence: float = 1.0,
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> list[Event]:
        text = transcript.strip()
        if not text:
            return []

        when = now or datetime.now(timezone.utc)
        started = Event.create(
            topics.VOICE_ACTIVITY_STARTED,
            "audio.terminal_input",
            payload={"text": text},
            trace_id=trace_id,
            timestamp=when,
        )
        normalized = self.normalizer.normalize(
            text,
            confidence=confidence,
            trace_id=started.trace_id,
            now=when,
        )
        ended = Event.create(
            topics.VOICE_ACTIVITY_ENDED,
            "audio.terminal_input",
            payload={"text": text},
            trace_id=started.trace_id,
            timestamp=when,
        )
        if normalized is None:
            return [started, ended]
        return [started, normalized, ended]
