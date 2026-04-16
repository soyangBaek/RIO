"""Transcript injection — simulate STT output by calling
:class:`IntentNormalizer.normalize` directly and publishing the resulting
``voice.*`` events. Useful for VOICE-* scenarios without a mic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.core.events import Event, topics  # noqa: E402
from app.adapters.audio.intent_normalizer import IntentNormalizer  # noqa: E402
from app.domains.speech import IntentDedupe, IntentParser  # noqa: E402


def default_aliases() -> dict:
    return {
        "camera.capture": ["사진 찍어줘", "photo"],
        "timer.create": ["타이머"],
        "smarthome.aircon.on": ["에어컨 켜줘"],
        "weather.current": ["날씨 알려줘"],
        "system.cancel": ["취소"],
    }


def build_normalizer(
    aliases: Optional[dict] = None,
    stt_confidence_min: float = 0.5,
    intent_match_min: float = 0.6,
) -> IntentNormalizer:
    parser = IntentParser(aliases or default_aliases(), min_confidence=intent_match_min)
    return IntentNormalizer(
        parser=parser, dedupe=IntentDedupe(cooldown_ms=1_500),
        stt_confidence_min=stt_confidence_min,
    )


def inject(
    entries: Iterable[Tuple[float, str, float]],
    publish: Callable[[Event], None],
    normalizer: Optional[IntentNormalizer] = None,
) -> int:
    """Each entry is ``(timestamp_monotonic, text, stt_confidence)``.

    The helper emits ``voice.activity.started`` / ``voice.activity.ended``
    bracketing every transcript, then the normalized intent event.
    Returns the number of *intent* events produced (non-dedupe'd).
    """
    norm = normalizer or build_normalizer()
    count = 0
    for ts, text, confidence in entries:
        publish(
            Event(topic=topics.VOICE_ACTIVITY_STARTED, timestamp=ts,
                  source="transcript_injection")
        )
        e = norm.normalize(text, stt_confidence=confidence, now=ts + 0.1)
        publish(
            Event(topic=topics.VOICE_ACTIVITY_ENDED, timestamp=ts + 0.2,
                  source="transcript_injection")
        )
        if e is not None:
            publish(e)
            if e.topic == topics.VOICE_INTENT_DETECTED:
                count += 1
    return count


def test_injection_detects_known_and_unknown():
    emitted: List[Event] = []
    inject(
        [(1.0, "사진 찍어줘", 0.9), (2.0, "모르는 말", 0.9)],
        emitted.append,
    )
    detected = [e for e in emitted if e.topic == topics.VOICE_INTENT_DETECTED]
    unknown = [e for e in emitted if e.topic == topics.VOICE_INTENT_UNKNOWN]
    assert len(detected) == 1 and detected[0].payload["intent"] == "camera.capture"
    assert len(unknown) == 1


if __name__ == "__main__":
    test_injection_detects_known_and_unknown()
    print("ok: transcript_injection self-test")
