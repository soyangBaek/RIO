from __future__ import annotations

from threading import RLock
from typing import Callable, TypeVar

from src.app.core.state.models import RuntimeState


T = TypeVar("T")


class RuntimeStore:
    """Thread-safe runtime state container for the main process."""

    def __init__(self, initial: RuntimeState | None = None) -> None:
        self._state = initial or RuntimeState()
        self._lock = RLock()

    def snapshot(self) -> RuntimeState:
        with self._lock:
            return self._state.copy()

    def replace(self, state: RuntimeState) -> RuntimeState:
        with self._lock:
            self._state = state.copy()
            return self._state.copy()

    def mutate(self, mutator: Callable[[RuntimeState], T]) -> tuple[RuntimeState, T]:
        with self._lock:
            value = mutator(self._state)
            return self._state.copy(), value
