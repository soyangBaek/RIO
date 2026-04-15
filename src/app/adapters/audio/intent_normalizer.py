from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.domains.speech.dedupe import IntentDeduper
from src.app.domains.speech.intent_parser import DEFAULT_INTENT_MATCH_CONFIDENCE_MIN, parse_intent
from src.app.domains.speech.timer_parser import parse_timer_text


@dataclass(slots=True)
class IntentNormalizer:
    deduper: IntentDeduper | None = None
    intent_match_confidence_min: float = DEFAULT_INTENT_MATCH_CONFIDENCE_MIN

    def normalize(
        self,
        transcript: str,
        *,
        confidence: float,
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> Event | None:
        when = now or datetime.now(timezone.utc)
        parsed = parse_intent(
            transcript,
            stt_confidence=confidence,
            intent_match_confidence_min=self.intent_match_confidence_min,
        )
        if not parsed.is_known:
            return Event.create(
                topics.VOICE_INTENT_UNKNOWN,
                "audio.intent_normalizer",
                payload={"text": transcript, "reason": parsed.reason},
                confidence=parsed.confidence,
                trace_id=trace_id,
                timestamp=when,
            )

        payload = {
            "intent": parsed.intent,
            "text": transcript,
            "matched_alias": parsed.matched_alias,
        }
        if parsed.intent == "timer.create":
            timer_parse = parse_timer_text(transcript, now=when)
            if not timer_parse.ok:
                return Event.create(
                    topics.VOICE_INTENT_UNKNOWN,
                    "audio.intent_normalizer",
                    payload={"text": transcript, "reason": timer_parse.error},
                    confidence=parsed.confidence,
                    trace_id=trace_id,
                    timestamp=when,
                )
            payload.update(timer_parse.payload)

        if self.deduper and not self.deduper.accept(parsed.intent, now=when):
            return None

        return Event.create(
            topics.VOICE_INTENT_DETECTED,
            "audio.intent_normalizer",
            payload=payload,
            confidence=parsed.confidence,
            trace_id=trace_id,
            timestamp=when,
        )
