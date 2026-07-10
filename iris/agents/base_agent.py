"""Base contract for all IRIS agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from iris.utils.status import AgentStatus

if TYPE_CHECKING:
    from iris.services.event_bus import Event, EventBus


class BaseAgent(ABC):
    """Abstract base class for future IRIS agents."""

    def __init__(self, name: str, version: str, event_bus: EventBus | None = None) -> None:
        self._name = name
        self._version = version
        self._status = AgentStatus.CREATED
        self._event_bus = event_bus

    @property
    def name(self) -> str:
        """Return the agent name."""
        return self._name

    @property
    def version(self) -> str:
        """Return the agent version."""
        return self._version

    @property
    def status(self) -> AgentStatus:
        """Return the current agent status."""
        return self._status

    def attach_event_bus(self, event_bus: EventBus) -> None:
        """Attach the event bus used for all agent communication."""
        self._event_bus = event_bus

    async def publish_event(self, event: Event) -> None:
        """Publish an event through the attached event bus."""
        if self._event_bus is None:
            raise RuntimeError("Agent event bus is not configured")

        await self._event_bus.publish(event)

    def subscribe_event(
        self,
        event_name: str,
        handler: Callable[["Event"], None | Awaitable[None]],
    ) -> None:
        """Subscribe to an event through the attached event bus."""
        if self._event_bus is None:
            raise RuntimeError("Agent event bus is not configured")

        self._event_bus.subscribe(event_name, handler)

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the agent for execution."""

    @abstractmethod
    def run(self) -> None:
        """Run the agent."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the agent."""

    @abstractmethod
    def health(self) -> bool:
        """Return True when the agent is healthy."""
