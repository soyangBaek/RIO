from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict

from src.app.core.events.models import Event


Subscriber = Callable[[Event], None]


class EventRouter:
    """Simple in-process pub/sub router used by the main orchestrator."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, list[Subscriber]] = defaultdict(list)
        self._wildcard_subscribers: list[Subscriber] = []

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        if topic == "*":
            self._wildcard_subscribers.append(handler)
            return
        self._subscribers[topic].append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._subscribers.get(event.topic, []):
            handler(event)
        for handler in self._wildcard_subscribers:
            handler(event)

