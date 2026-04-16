from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind
from src.app.domains.behavior.executor_registry import ExecutionRequest, ExecutionResult


@dataclass(slots=True)
class GamesService:
    def __call__(self, request: ExecutionRequest) -> ExecutionResult:
        task_id = str(request.payload.get("task_id") or uuid4().hex)
        started = Event.create(
            topics.TASK_STARTED,
            "games.service",
            payload={"task_id": task_id, "kind": ActionKind.GAME.value, "intent": request.intent},
            trace_id=request.trace_id,
            timestamp=datetime.now(timezone.utc),
        )
        succeeded = Event.create(
            topics.TASK_SUCCEEDED,
            "games.service",
            payload={
                "task_id": task_id,
                "kind": ActionKind.GAME.value,
                "ui_mode": "game",
                "message": "Game mode ready",
            },
            trace_id=request.trace_id,
        )
        return ExecutionResult(events=[started, succeeded], metadata={"ui_mode": "game"})
