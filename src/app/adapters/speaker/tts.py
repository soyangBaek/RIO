from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TTSPlayer:
    """Minimal text-to-speech abstraction used by tests and the main loop."""

    history: list[str] = field(default_factory=list)

    def speak(self, text: str) -> str:
        self.history.append(text)
        return text

