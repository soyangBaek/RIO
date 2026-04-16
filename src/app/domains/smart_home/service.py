"""Smart-home domain service.

Routes ``smarthome.*`` intents (scenarios VOICE-10..14, INT-07/08) through
the home-client adapter. On ``start`` it issues the HTTP call on a
background thread and emits ``task.succeeded`` / ``task.failed`` plus the
``smarthome.result`` observation event when the response returns.

The service is defensive against home-client failure (OPS-02): timeouts
and non-2xx responses become ``task.failed`` with the error attached.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional, Protocol

from ...core.events import topics
from ...core.events.models import Event, new_trace_id
from .payloads import build_request, is_smarthome_intent

_log = logging.getLogger(__name__)
Publisher = Callable[[Event], None]


class HomeClient(Protocol):
    def send_command(self, body: dict) -> dict:
        """Return a dict with keys ``ok`` (bool), ``status`` (int), and optional ``error``."""
        ...


class SmartHomeService:
    def __init__(
        self,
        publish: Publisher,
        client: HomeClient,
        devices: Optional[Dict[str, str]] = None,
    ) -> None:
        self._publish = publish
        self._client = client
        self._devices = devices or {}
        self._task_seq = 0
        self._active_task_id: Optional[str] = None
        self._cancelled = threading.Event()

    # -- ExecutorHandler protocol ------------------------------------------
    def start(self, context: dict) -> None:
        payload = context.get("payload") or {}
        trace_id = context.get("trace_id") or new_trace_id()
        intent_id = payload.get("intent")

        if not isinstance(intent_id, str) or not is_smarthome_intent(intent_id):
            self._fail(trace_id=trace_id, error="unknown_intent")
            return

        body = build_request(intent_id, self._devices)
        if body is None:
            self._fail(trace_id=trace_id, error="no_payload")
            return

        self._task_seq += 1
        task_id = f"smarthome_{self._task_seq}"
        self._active_task_id = task_id
        self._cancelled.clear()

        self._publish(
            Event(
                topic=topics.TASK_STARTED,
                payload={"task_id": task_id, "kind": "smarthome", "intent": intent_id},
                trace_id=trace_id,
                source="smart_home",
            )
        )
        self._publish(
            Event(
                topic=topics.SMARTHOME_REQUEST_SENT,
                payload={"intent": intent_id, "content": body.get("content")},
                trace_id=trace_id,
                source="smart_home",
            )
        )

        thread = threading.Thread(
            target=self._send_and_emit,
            args=(task_id, intent_id, body, trace_id),
            daemon=True,
            name=f"smarthome-{task_id}",
        )
        thread.start()

    def cancel(self) -> None:
        self._cancelled.set()
        self._active_task_id = None

    # -- internals ----------------------------------------------------------
    def _send_and_emit(
        self,
        task_id: str,
        intent_id: str,
        body: dict,
        trace_id: str,
    ) -> None:
        try:
            result = self._client.send_command(body)
        except Exception as e:
            _log.exception("home_client call raised")
            result = {"ok": False, "status": 0, "error": str(e)}

        if self._cancelled.is_set() and self._active_task_id != task_id:
            # Drop results for cancelled tasks.
            return

        ok = bool(result.get("ok"))
        self._publish(
            Event(
                topic=topics.SMARTHOME_RESULT,
                payload={
                    "intent": intent_id,
                    "ok": ok,
                    "status": result.get("status"),
                    "error": result.get("error"),
                },
                trace_id=trace_id,
                source="smart_home",
            )
        )
        self._publish(
            Event(
                topic=topics.TASK_SUCCEEDED if ok else topics.TASK_FAILED,
                payload={
                    "task_id": task_id,
                    "kind": "smarthome",
                    "intent": intent_id,
                    "error": None if ok else result.get("error") or "failed",
                },
                trace_id=trace_id,
                source="smart_home",
            )
        )

    def _fail(self, trace_id: str, error: str) -> None:
        self._task_seq += 1
        task_id = f"smarthome_{self._task_seq}"
        self._publish(
            Event(
                topic=topics.TASK_FAILED,
                payload={"task_id": task_id, "kind": "smarthome", "error": error},
                trace_id=trace_id,
                source="smart_home",
            )
        )
