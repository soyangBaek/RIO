"""T-031: Executor registry – Executing(kind)별 도메인 핸들러 선택.

kind → handler 매핑. task lifecycle 이벤트 관리.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)

# Handler 시그니처: (payload, callback) → None
# callback 은 완료 시 호출하며 Event 반환
Handler = Callable[[Dict[str, Any], Callable[[Event], None]], None]


class ExecutorRegistry:
    """Executing(kind) 별 도메인 핸들러 등록 및 호출."""

    def __init__(self) -> None:
        self._handlers: Dict[str, Handler] = {}
        self._active_task: Optional[str] = None

    def register(self, kind: str, handler: Handler) -> None:
        """kind 에 핸들러 등록."""
        self._handlers[kind] = handler
        logger.info("Executor registered: %s", kind)

    def execute(
        self,
        kind: str,
        payload: Dict[str, Any],
        on_complete: Callable[[Event], None],
    ) -> Optional[str]:
        """kind 의 핸들러를 실행. task_id 반환."""
        handler = self._handlers.get(kind)
        if handler is None:
            logger.warning("No handler for kind: %s", kind)
            on_complete(
                Event(
                    topic=Topics.TASK_FAILED,
                    source="main/executor",
                    payload={"kind": kind, "error": f"No handler for {kind}"},
                )
            )
            return None

        task_id = uuid.uuid4().hex[:8]
        self._active_task = task_id
        now = time.time()

        # task.started 이벤트
        on_complete(
            Event(
                topic=Topics.TASK_STARTED,
                source="main/executor",
                payload={"task_id": task_id, "kind": kind},
                timestamp=now,
            )
        )

        def _done_callback(success: bool, result: Optional[Dict] = None, error: str = "") -> None:
            self._active_task = None
            if success:
                on_complete(
                    Event(
                        topic=Topics.TASK_SUCCEEDED,
                        source="main/executor",
                        payload={"task_id": task_id, "kind": kind, "result": result or {}},
                    )
                )
            else:
                on_complete(
                    Event(
                        topic=Topics.TASK_FAILED,
                        source="main/executor",
                        payload={"task_id": task_id, "kind": kind, "error": error},
                    )
                )

        try:
            handler(
                {**payload, "task_id": task_id},
                _done_callback,
            )
        except Exception as e:
            logger.exception("Handler error for %s", kind)
            _done_callback(False, error=str(e))

        return task_id

    @property
    def active_task(self) -> Optional[str]:
        return self._active_task

    @property
    def registered_kinds(self) -> List[str]:
        return list(self._handlers.keys())
