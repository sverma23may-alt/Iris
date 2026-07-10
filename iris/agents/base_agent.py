"""Base contract for all IRIS agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from iris.utils.status import AgentStatus


class BaseAgent(ABC):
    """Abstract base class for future IRIS agents."""

    def __init__(self, name: str, version: str) -> None:
        self._name = name
        self._version = version
        self._status = AgentStatus.CREATED

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
