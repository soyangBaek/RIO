from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind
from src.app.domains.behavior.executor_registry import ExecutionRequest, ExecutionResult


class TimerSchedulerPort(Protocol):
    def add_timer(
        self,
        delay_seconds: float,
        label: str = "",
        *,
        timer_id: str | None = None,
        now: datetime | None = None,
    ):
        ...


@dataclass(slots=True)
class TimerService:
    scheduler: TimerSchedulerPort

    def __call__(self, request: ExecutionRequest) -> ExecutionResult:
        task_id = str(request.payload.get("task_id") or uuid4().hex)
        delay_seconds = float(request.payload.get("delay_seconds") or 0)
        label = str(request.payload.get("label") or request.payload.get("spoken_text") or "Timer")

        started = Event.create(
            topics.TASK_STARTED,
            "timers.service",
            payload={"task_id": task_id, "kind": ActionKind.TIMER_SETUP.value, "label": label},
            trace_id=request.trace_id,
            timestamp=datetime.now(timezone.utc),
        )
        if delay_seconds <= 0:
            failed = Event.create(
                topics.TASK_FAILED,
                "timers.service",
                payload={
                    "task_id": task_id,
                    "kind": ActionKind.TIMER_SETUP.value,
                    "message": "delay_seconds must be positive",
                },
                trace_id=request.trace_id,
            )
            return ExecutionResult(events=[started, failed])

        timer_record = self.scheduler.add_timer(
            delay_seconds=delay_seconds,
            label=label,
            timer_id=str(request.payload.get("timer_id") or uuid4().hex),
        )
        succeeded = Event.create(
            topics.TASK_SUCCEEDED,
            "timers.service",
            payload={
                "task_id": task_id,
                "kind": ActionKind.TIMER_SETUP.value,
                "timer_id": timer_record.timer_id,
                "label": label,
                "delay_seconds": delay_seconds,
            },
            trace_id=request.trace_id,
        )
        return ExecutionResult(events=[started, succeeded], metadata={"timer_id": timer_record.timer_id})
