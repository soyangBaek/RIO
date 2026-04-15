from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class Transcript:
    text: str
    confidence: float


class SpeechToTextAdapter:
    def __init__(
        self,
        engine: Callable[[Any], Transcript | tuple[str, float] | str | None] | None = None,
        *,
        confidence_min: float = 0.5,
    ) -> None:
        self.engine = engine
        self.confidence_min = confidence_min

    def transcribe(self, frame: Any) -> Transcript:
        if isinstance(frame, dict) and "transcript" in frame:
            return Transcript(str(frame["transcript"]), float(frame.get("confidence", 1.0)))
        if self.engine is None:
            if isinstance(frame, (bytes, bytearray)):
                try:
                    return Transcript(frame.decode("utf-8"), 0.8)
                except UnicodeDecodeError:
                    return Transcript("", 0.0)
            return Transcript("", 0.0)
        result = self.engine(frame)
        if result is None:
            return Transcript("", 0.0)
        if isinstance(result, Transcript):
            return result
        if isinstance(result, tuple):
            text, confidence = result
            return Transcript(str(text), float(confidence))
        return Transcript(str(result), 1.0)
