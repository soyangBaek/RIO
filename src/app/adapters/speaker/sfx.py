from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SFXPlayer:
    """A lightweight effect player that records requested sounds."""

    history: list[str] = field(default_factory=list)

    def play(self, name: str) -> str:
        self.history.append(name)
        return name

