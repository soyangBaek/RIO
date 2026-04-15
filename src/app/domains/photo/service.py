from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind
from src.app.domains.behavior.executor_registry import ExecutionRequest, ExecutionResult


class PhotoCapturePort(Protocol):
    def capture(self, *, trace_id: str | None = None) -> str:
        ...


@dataclass(slots=True)
class PhotoService:
    capture_port: PhotoCapturePort
    countdown_seconds: int = 3

    def __call__(self, request: ExecutionRequest) -> ExecutionResult:
        task_id = str(request.payload.get("task_id") or uuid4().hex)
        now = datetime.now(timezone.utc)
        started = Event.create(
            topics.TASK_STARTED,
            "photo.service",
            payload={
                "task_id": task_id,
                "kind": ActionKind.PHOTO.value,
                "countdown": list(range(self.countdown_seconds, 0, -1)),
            },
            trace_id=request.trace_id,
            timestamp=now,
        )
        try:
            photo_path = self.capture_port.capture(trace_id=request.trace_id)
        except Exception as exc:  # pragma: no cover - defensive
            failed = Event.create(
                topics.TASK_FAILED,
                "photo.service",
                payload={
                    "task_id": task_id,
                    "kind": ActionKind.PHOTO.value,
                    "message": str(exc),
                },
                trace_id=request.trace_id,
            )
            return ExecutionResult(events=[started, failed])

        succeeded = Event.create(
            topics.TASK_SUCCEEDED,
            "photo.service",
            payload={
                "task_id": task_id,
                "kind": ActionKind.PHOTO.value,
                "photo_path": photo_path,
                "countdown": list(range(self.countdown_seconds, 0, -1)),
            },
            trace_id=request.trace_id,
        )
        return ExecutionResult(events=[started, succeeded], metadata={"photo_path": photo_path})
