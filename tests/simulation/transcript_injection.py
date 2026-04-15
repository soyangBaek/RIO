from __future__ import annotations

from datetime import datetime, timezone

from src.app.adapters.audio.intent_normalizer import IntentNormalizer


def inject_transcript(text: str, *, confidence: float = 0.95):
    normalizer = IntentNormalizer()
    return normalizer.normalize(text, confidence=confidence, now=datetime.now(timezone.utc))


if __name__ == "__main__":
    print(inject_transcript("사진 찍어줘"))
