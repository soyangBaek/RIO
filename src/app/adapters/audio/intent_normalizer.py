"""Audio-worker-side intent normalisation.

Takes STT output (``text`` + ``confidence``) and converts it into the bus
event the main orchestrator should see:

- ``voice.intent.detected`` with the canonical intent id and slots.
- ``voice.intent.unknown`` when confidence gates fail or the parser cannot
  match an alias (VOICE-02).

Also runs timer duration parsing for ``timer.create`` so the payload
carries a ``duration_s`` slot that :class:`TimerService` can consume
without re-parsing.

The normalizer is stateful (it owns the dedupe window) and is meant to be
instantiated once per audio worker.
"""
from __future__ import annotations

import logging
from typing import Optional

from ...core.events import topics
from ...core.events.models import Event, new_trace_id
from ...domains.speech.dedupe import IntentDedupe
from ...domains.speech.intent_parser import IntentParser
from ...domains.speech.timer_parser import parse_duration

_log = logging.getLogger(__name__)


class IntentNormalizer:
    def __init__(
        self,
        parser: IntentParser,
        dedupe: IntentDedupe,
        stt_confidence_min: float = 0.5,
    ) -> None:
        self._parser = parser
        self._dedupe = dedupe
        self._stt_min = stt_confidence_min

    def normalize(
        self,
        text: str,
        stt_confidence: float,
        now: float,
    ) -> Optional[Event]:
        """Return the event to publish, or ``None`` to drop (dedupe hit)."""
        # STT confidence gate — below threshold is always unknown.
        if stt_confidence < self._stt_min or not text.strip():
            return _unknown(text=text, confidence=stt_confidence, now=now)

        parsed = self._parser.parse(text, stt_confidence=stt_confidence)
        if parsed is None:
            return _unknown(text=text, confidence=stt_confidence, now=now)

        if not self._dedupe.should_accept(parsed.intent_id, now):
            return None

        payload = {
            "intent": parsed.intent_id,
            "text": text,
            "confidence": parsed.combined_confidence,
        }
        # Slot fill for timer.create.
        if parsed.intent_id == "timer.create":
            duration_s = parse_duration(text)
            if duration_s is None:
                # Parsed as timer intent but no duration extractable —
                # emit unknown so a confused oneshot fires (VOICE-08).
                return _unknown(text=text, confidence=stt_confidence, now=now)
            payload["duration_s"] = duration_s

        return Event(
            topic=topics.VOICE_INTENT_DETECTED,
            payload=payload,
            timestamp=now,
            trace_id=new_trace_id(),
            source="audio_worker",
        )


def _unknown(text: str, confidence: float, now: float) -> Event:
    return Event(
        topic=topics.VOICE_INTENT_UNKNOWN,
        payload={"text": text, "confidence": confidence},
        timestamp=now,
        trace_id=new_trace_id(),
        source="audio_worker",
    )
