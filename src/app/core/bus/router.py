"""In-process event router — the main loop's dispatch core.

The router owns handler registrations and fans out events to subscribers
synchronously. It also knows how to *pump* an :class:`EventBus` (the
cross-process worker→main queue) into its own dispatch path so that worker
events and in-process events share a single ordering contract.

Design points
-------------
- Dispatch is synchronous and single-threaded. Architecture §2 requires the
  main loop to process one event at a time so FSM reducers stay race-free.
- Exact-topic subscriptions fire first, then domain subscriptions
  (e.g. every ``vision.*``), then :meth:`subscribe_all` handlers. More
  specific subscriptions usually carry the authoritative FSM transition, so
  they see the event before broad observers such as logging.
- Handler exceptions are logged and swallowed. A failing subscriber cannot
  starve the loop or suppress later subscribers for the same event.
- Registration order is preserved within each layer.
"""
from __future__ import annotations

import itertools
import logging
from typing import Callable, Dict, List, Optional

from ..events.models import Event
from ..events.topics import domain_of
from .queue_bus import EventBus

_log = logging.getLogger(__name__)

Handler = Callable[[Event], None]


class _Subscription:
    __slots__ = ("id", "kind", "key", "handler")

    def __init__(self, sub_id: int, kind: str, key: str, handler: Handler) -> None:
        self.id = sub_id
        self.kind = kind  # "topic" | "domain" | "all"
        self.key = key
        self.handler = handler


class Router:
    """Synchronous in-process pub/sub for the main orchestrator."""

    def __init__(self) -> None:
        self._by_topic: Dict[str, List[_Subscription]] = {}
        self._by_domain: Dict[str, List[_Subscription]] = {}
        self._all: List[_Subscription] = []
        self._ids = itertools.count(1)

    # -- registration -------------------------------------------------------
    def subscribe(self, topic: str, handler: Handler) -> int:
        sub = _Subscription(next(self._ids), "topic", topic, handler)
        self._by_topic.setdefault(topic, []).append(sub)
        return sub.id

    def subscribe_domain(self, domain: str, handler: Handler) -> int:
        sub = _Subscription(next(self._ids), "domain", domain, handler)
        self._by_domain.setdefault(domain, []).append(sub)
        return sub.id

    def subscribe_all(self, handler: Handler) -> int:
        sub = _Subscription(next(self._ids), "all", "", handler)
        self._all.append(sub)
        return sub.id

    def unsubscribe(self, sub_id: int) -> bool:
        for subs in self._by_topic.values():
            for s in subs:
                if s.id == sub_id:
                    subs.remove(s)
                    return True
        for subs in self._by_domain.values():
            for s in subs:
                if s.id == sub_id:
                    subs.remove(s)
                    return True
        for s in self._all:
            if s.id == sub_id:
                self._all.remove(s)
                return True
        return False

    def subscription_count(self) -> int:
        return (
            sum(len(v) for v in self._by_topic.values())
            + sum(len(v) for v in self._by_domain.values())
            + len(self._all)
        )

    # -- dispatch -----------------------------------------------------------
    def dispatch(self, event: Event) -> int:
        """Fan out ``event`` to every matching subscriber.

        Returns the number of handlers invoked (including those that raised).
        """
        ordered: List[_Subscription] = []
        ordered.extend(self._by_topic.get(event.topic, ()))
        try:
            ordered.extend(self._by_domain.get(domain_of(event.topic), ()))
        except ValueError:
            _log.warning("event with malformed topic ignored: %r", event.topic)
        ordered.extend(self._all)

        for sub in ordered:
            try:
                sub.handler(event)
            except Exception:  # noqa: BLE001 — subscriber isolation
                _log.exception(
                    "handler #%d failed for topic %s", sub.id, event.topic
                )
        return len(ordered)

    # In-process publish is just a synchronous dispatch. Workers publish via
    # EventBus, not through this method.
    publish = dispatch

    # -- bus bridge ---------------------------------------------------------
    def pump(
        self,
        bus: EventBus,
        max_items: int = 64,
        timeout: Optional[float] = None,
    ) -> int:
        """Move events from ``bus`` into the dispatch path.

        If ``timeout`` is given, wait up to that many seconds for the first
        event; then drain whatever else is already queued (non-blocking) up to
        ``max_items`` total. Returns the number of events dispatched.
        """
        count = 0
        remaining = max_items
        if timeout is not None and remaining > 0:
            first = bus.poll(timeout=timeout)
            if first is not None:
                self.dispatch(first)
                count += 1
                remaining -= 1
        if remaining > 0:
            for event in bus.drain(remaining):
                self.dispatch(event)
                count += 1
        return count
