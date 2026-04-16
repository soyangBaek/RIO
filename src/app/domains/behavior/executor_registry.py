"""Route ``Executing(kind)`` transitions to domain-specific handlers.

Domain services (``domains/photo``, ``domains/timers``, ``domains/smart_home``,
``domains/games``) register a :class:`ExecutorHandler` per
:class:`ExecutingKind` they own. The registry listens to
``activity.state.changed`` and calls ``start`` when the activity enters
that kind, and ``cancel`` when it leaves while still running.

Handlers are expected to publish ``task.started`` / ``task.succeeded``
or ``task.failed`` on their own; the registry does not wrap them.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Optional, Protocol

from ...core.events import topics
from ...core.events.models import Event
from ...core.state.models import ExecutingKind

_log = logging.getLogger(__name__)


class ExecutorHandler(Protocol):
    def start(self, context: dict) -> None: ...
    def cancel(self) -> None: ...


def _parse_activity_label(label: str) -> Optional[str]:
    """Extract the kind from ``executing(photo)``-style labels."""
    if label.startswith("executing(") and label.endswith(")"):
        return label[len("executing("):-1]
    return None


class ExecutorRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[ExecutingKind, ExecutorHandler] = {}
        self._running: Optional[ExecutingKind] = None

    def register(self, kind: ExecutingKind, handler: ExecutorHandler) -> None:
        self._handlers[kind] = handler

    def registered_kinds(self) -> Dict[ExecutingKind, ExecutorHandler]:
        return dict(self._handlers)

    def on_activity_changed(self, event: Event) -> None:
        if event.topic != topics.ACTIVITY_STATE_CHANGED:
            return

        from_label = str(event.payload.get("from", ""))
        to_label = str(event.payload.get("to", ""))
        from_kind_str = _parse_activity_label(from_label)
        to_kind_str = _parse_activity_label(to_label)

        # Leaving executing: cancel the currently running handler if any.
        if from_kind_str is not None and to_kind_str != from_kind_str:
            self._cancel_running()

        if to_kind_str is not None:
            try:
                new_kind = ExecutingKind(to_kind_str)
            except ValueError:
                _log.warning("unknown executing kind %r", to_kind_str)
                return
            handler = self._handlers.get(new_kind)
            if handler is None:
                _log.info("no executor registered for kind=%s", new_kind.value)
                return
            self._running = new_kind
            try:
                handler.start({"trace_id": event.trace_id, "payload": event.payload})
            except Exception:
                _log.exception("executor start failed for %s", new_kind.value)

    def _cancel_running(self) -> None:
        kind = self._running
        if kind is None:
            return
        handler = self._handlers.get(kind)
        self._running = None
        if handler is None:
            return
        try:
            handler.cancel()
        except Exception:
            _log.exception("executor cancel failed for %s", kind.value)
