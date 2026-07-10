"""Central lifecycle coordinator for IRIS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.agents.base_agent import BaseAgent
from iris.agents.manager import AgentManager
from iris.services.logger import get_logger
from iris.utils.status import ServiceStatus


@dataclass(frozen=True)
class IrisStatus:
    """Snapshot of the IRIS runtime state."""

    status: ServiceStatus
    registered_agents: int

    def to_dict(self) -> dict[str, Any]:
        """Return the status snapshot as primitive values."""
        return {
            "status": self.status.value,
            "registered_agents": self.registered_agents,
        }


class IrisCore:
    """Coordinates IRIS platform startup, shutdown, and agent registration."""

    def __init__(self, agent_manager: AgentManager | None = None) -> None:
        self._logger = get_logger(__name__)
        self._agent_manager = agent_manager or AgentManager()
        self._status = ServiceStatus.OFFLINE

    @property
    def status(self) -> ServiceStatus:
        """Return the current core status."""
        return self._status

    def start(self) -> None:
        """Mark the IRIS core as online."""
        if self._status is ServiceStatus.ONLINE:
            self._logger.debug("IRIS core already online")
            return

        self._status = ServiceStatus.ONLINE
        self._logger.info("IRIS core started")

    def stop(self) -> None:
        """Stop all registered agents and mark the IRIS core as offline."""
        if self._status is ServiceStatus.OFFLINE:
            self._logger.debug("IRIS core already offline")
            return

        for agent in self._agent_manager.list_agents():
            agent.stop()

        self._status = ServiceStatus.OFFLINE
        self._logger.info("IRIS core stopped")

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the platform."""
        self._agent_manager.register(agent)
        self._logger.info("Registered agent: {}", agent.name)

    def unregister_agent(self, name: str) -> None:
        """Unregister an agent by name."""
        self._agent_manager.unregister(name)
        self._logger.info("Unregistered agent: {}", name)

    def get_status(self) -> IrisStatus:
        """Return a snapshot of the current platform status."""
        return IrisStatus(
            status=self._status,
            registered_agents=len(self._agent_manager.list_agents()),
        )
