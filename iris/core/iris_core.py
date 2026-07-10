"""Central lifecycle coordinator for IRIS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.agents.base_agent import BaseAgent
from iris.agents.manager import AgentManager
from iris.services.async_runtime import AsyncRuntime
from iris.services.background_worker import BackgroundWorker
from iris.services.event_bus import EventBus
from iris.services.logger import get_logger
from iris.services.plugin_loader import PluginLoader
from iris.services.task_queue import TaskQueue
from iris.utils.status import ServiceStatus


@dataclass(frozen=True)
class IrisStatus:
    """Snapshot of the IRIS runtime state."""

    status: ServiceStatus
    registered_agents: int
    queue_size: int
    running_tasks: int
    completed_tasks: int

    def to_dict(self) -> dict[str, Any]:
        """Return the status snapshot as primitive values."""
        return {
            "status": self.status.value,
            "registered_agents": self.registered_agents,
            "queue_size": self.queue_size,
            "running_tasks": self.running_tasks,
            "completed_tasks": self.completed_tasks,
        }


class IrisCore:
    """Coordinates IRIS platform startup, shutdown, and agent registration."""

    def __init__(
        self,
        agent_manager: AgentManager | None = None,
        event_bus: EventBus | None = None,
        task_queue: TaskQueue | None = None,
        async_runtime: AsyncRuntime | None = None,
    ) -> None:
        self._logger = get_logger(__name__)
        self._agent_manager = agent_manager or AgentManager()
        self._event_bus = event_bus or EventBus()
        self._task_queue = task_queue or TaskQueue()
        self._async_runtime = async_runtime or AsyncRuntime()
        self._worker = BackgroundWorker(self._task_queue, self._event_bus)
        self._plugin_loader = PluginLoader(event_bus=self._event_bus)
        self._status = ServiceStatus.OFFLINE

    @property
    def status(self) -> ServiceStatus:
        """Return the current core status."""
        return self._status

    @property
    def event_bus(self) -> EventBus:
        """Return the platform event bus."""
        return self._event_bus

    @property
    def task_queue(self) -> TaskQueue:
        """Return the platform task queue."""
        return self._task_queue

    def start(self) -> None:
        """Mark the IRIS core as online."""
        if self._status is ServiceStatus.ONLINE:
            self._logger.debug("IRIS core already online")
            return

        self._async_runtime.start()
        self._async_runtime.submit(self._worker.start()).result(timeout=5)
        self._register_discovered_plugins()
        self._status = ServiceStatus.ONLINE
        self._logger.info("IRIS core started")

    def stop(self) -> None:
        """Stop all registered agents and mark the IRIS core as offline."""
        if self._status is ServiceStatus.OFFLINE:
            self._logger.debug("IRIS core already offline")
            return

        for agent in self._agent_manager.list_agents():
            agent.stop()

        self._async_runtime.submit(self._worker.stop()).result(timeout=5)
        self._async_runtime.stop()
        self._status = ServiceStatus.OFFLINE
        self._logger.info("IRIS core stopped")

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the platform."""
        agent.attach_event_bus(self._event_bus)
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
            queue_size=self._task_queue.queue_size(),
            running_tasks=self._task_queue.running_count(),
            completed_tasks=self._task_queue.completed_count(),
        )

    def _register_discovered_plugins(self) -> None:
        """Register discovered plugin agents."""
        for agent in self._plugin_loader.discover():
            if self._agent_manager.get_agent(agent.name) is not None:
                self._logger.warning("Skipping duplicate plugin agent: {}", agent.name)
                continue

            self.register_agent(agent)
