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

    def reset_all(self) -> dict[str, object]:  # pragma: no cover - optional
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
        if request.intent == "smarthome.all.off":
            return self._handle_all_off(request, task_id, started)
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
                or (f"{command.display_name} {command.action_label} done" if ok else f"{command.display_name} control failed")
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
                "request_method": response.get("request_method"),
                "request_content": response.get("request_content"),
                "bridge_status": "up" if ok else "down",
                "error_code": None if ok else response.get("message", "unknown_error"),
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

    def _handle_all_off(
        self,
        request: ExecutionRequest,
        task_id: str,
        started: Event,
    ) -> ExecutionResult:
        content = "all:off"
        reset_fn = getattr(self.client, "reset_all", None)
        request_sent = Event.create(
            topics.SMARTHOME_REQUEST_SENT,
            "smart_home.service",
            payload={
                "task_id": task_id,
                "intent": request.intent,
                "device_id": "all",
                "action": "off",
                "params": {},
                "content": content,
                "request_url": self._reset_url(),
                "transport": "http",
            },
            trace_id=request.trace_id,
        )
        try:
            if callable(reset_fn):
                response = reset_fn()
            else:
                response = {"ok": False, "message": "reset_all_not_supported"}
            ok = bool(response.get("ok", True))
            message = str(response.get("message") or ("All devices off" if ok else "Reset failed"))
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
                "device_id": "all",
                "action": "off",
                "params": {},
                "request_url": response.get("request_url"),
                "request_method": response.get("request_method"),
                "request_content": response.get("request_content", content),
                "bridge_status": "up" if ok else "down",
                "error_code": None if ok else response.get("message", "unknown_error"),
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
            metadata={"command": content, "params": {}},
        )

    def _reset_url(self) -> str | None:
        base = getattr(self.client, "base_url", None)
        if not base:
            return None
        return f"{str(base).rstrip('/')}/api/reset"
