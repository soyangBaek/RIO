from __future__ import annotations

from copy import deepcopy
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
            return deepcopy(self._state)

    def replace(self, state: RuntimeState) -> RuntimeState:
        with self._lock:
            self._state = deepcopy(state)
            return deepcopy(self._state)

    def mutate(self, mutator: Callable[[RuntimeState], T]) -> tuple[RuntimeState, T]:
        with self._lock:
            value = mutator(self._state)
            return deepcopy(self._state), value

