"""Global state store for the RIO main orchestrator.

The store owns the single :class:`State` instance that the reducers mutate and
adapters read. Architecture §2 makes the main loop single-threaded, but
rendering/audio adapters may poll the state from their own threads, so the
store protects its internal state with an :class:`~threading.RLock` and
exposes :meth:`snapshot` for cross-thread reads.
"""
from __future__ import annotations

import copy
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from .models import State


class StateStore:
    def __init__(self, initial: Optional[State] = None) -> None:
        self._state: State = initial if initial is not None else State()
        self._lock = threading.RLock()

    # -- reads --------------------------------------------------------------
    def get(self) -> State:
        """Return the live :class:`State` reference.

        Callers on the main thread read directly. Any mutation outside of
        :meth:`mutate` / :meth:`update` is a bug — use those for any write.
        """
        return self._state

    def snapshot(self) -> State:
        """Return a deep copy safe for cross-thread consumption."""
        with self._lock:
            return copy.deepcopy(self._state)

    # -- writes -------------------------------------------------------------
    @contextmanager
    def mutate(self) -> Iterator[State]:
        """Hold the lock while the caller mutates :class:`State` in place."""
        with self._lock:
            yield self._state

    def update(self, mutator: Callable[[State], None]) -> None:
        """Apply ``mutator(state)`` under the lock."""
        with self._lock:
            mutator(self._state)

    def replace(self, new_state: State) -> None:
        """Atomically swap the stored :class:`State`."""
        with self._lock:
            self._state = new_state
