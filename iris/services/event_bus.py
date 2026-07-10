"""In-process event bus for agent communication."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from iris.services.logger import get_logger


EventHandler = Callable[["Event"], None | Awaitable[None]]


@dataclass(frozen=True)
class Event:
    """Immutable message passed between agents through the event bus."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Publish-subscribe event bus used for agent communication."""

    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event name."""
        self._subscribers[event_name].append(handler)
        self._logger.debug("Subscribed handler to event: {}", event_name)

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers."""
        handlers = [*self._subscribers.get(event.name, []), *self._subscribers.get("*", [])]
        self._logger.debug("Publishing event {} to {} handlers", event.name, len(handlers))

        for handler in handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
