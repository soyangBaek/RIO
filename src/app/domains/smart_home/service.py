from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind
from src.app.domains.behavior.executor_registry import ExecutionRequest, ExecutionResult
from src.app.domains.smart_home.payloads import SmartHomeCommand, build_smart_home_command


class HomeClientPort(Protocol):
    def control(self, content: str) -> dict[str, object]:
        ...


@dataclass(slots=True)
class SmartHomeService:
    client: HomeClientPort

    def __call__(self, request: ExecutionRequest) -> ExecutionResult:
        task_id = str(request.payload.get("task_id") or uuid4().hex)
        started = Event.create(
            topics.TASK_STARTED,
            "smart_home.service",
            payload={"task_id": task_id, "kind": ActionKind.SMARTHOME.value, "intent": request.intent},
            trace_id=request.trace_id,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            command = build_smart_home_command(request.intent, payload=request.payload)
        except Exception as exc:
            failed = Event.create(
                topics.TASK_FAILED,
                "smart_home.service",
                payload={
                    "task_id": task_id,
                    "kind": ActionKind.SMARTHOME.value,
                    "message": str(exc),
                },
                trace_id=request.trace_id,
            )
            return ExecutionResult(events=[started, failed])

        request_sent = Event.create(
            topics.SMARTHOME_REQUEST_SENT,
            "smart_home.service",
            payload={
                "task_id": task_id,
                "intent": request.intent,
                "device_id": command.device_id,
                "action": command.action,
                "params": command.params,
                "content": command.content,
                "request_url": self._request_url(),
                "transport": "http",
            },
            trace_id=request.trace_id,
        )
        try:
            response = self.client.control(command.content)
            ok = bool(response.get("ok", True))
            message = str(
                response.get("message")
                or (f"{command.display_name} {command.action_label} 완료" if ok else f"{command.display_name} 제어 실패")
            )
        except Exception as exc:  # pragma: no cover - defensive
            ok = False
            response = {"error": str(exc)}
            message = str(exc)

        result = Event.create(
            topics.SMARTHOME_RESULT,
            "smart_home.service",
            payload={
                "task_id": task_id,
                "intent": request.intent,
                "ok": ok,
                "message": message,
                "device_id": command.device_id,
                "action": command.action,
                "params": command.params,
                "request_url": response.get("request_url"),
                "response": response,
            },
            trace_id=request.trace_id,
        )
        terminal_topic = topics.TASK_SUCCEEDED if ok else topics.TASK_FAILED
        terminal = Event.create(
            terminal_topic,
            "smart_home.service",
            payload={
                "task_id": task_id,
                "kind": ActionKind.SMARTHOME.value,
                "message": message,
            },
            trace_id=request.trace_id,
        )
        return ExecutionResult(
            events=[started, request_sent, result, terminal],
            metadata={"command": command.content, "params": command.params},
        )

    def _request_url(self) -> str | None:
        resolver = getattr(self.client, "resolve_control_url", None)
        if callable(resolver):
            value = resolver()
            return str(value) if value is not None else None
        return None
