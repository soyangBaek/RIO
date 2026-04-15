from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind


@dataclass(slots=True)
class ExecutionRequest:
    kind: ActionKind
    intent: str
    payload: dict[str, object]
    trace_id: str | None = None


@dataclass(slots=True)
class ExecutionResult:
    events: list[Event] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


Handler = Callable[[ExecutionRequest], ExecutionResult]


class ExecutorRegistry:
    def __init__(self) -> None:
        self._handlers: dict[ActionKind, Handler] = {}

    def register(self, kind: ActionKind, handler: Handler) -> None:
        self._handlers[kind] = handler

    def has_handler(self, kind: ActionKind) -> bool:
        return kind in self._handlers

    def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
        handler = self._handlers.get(request.kind)
        if handler is None:
            raise KeyError(f"No executor registered for {request.kind.value}")
        return handler(request)
