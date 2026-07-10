"""Central lifecycle coordinator for IRIS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.agents.base_agent import BaseAgent
from iris.agents.manager import AgentManager
from iris.services.async_runtime import AsyncRuntime
from iris.services.background_worker import BackgroundWorker
from iris.services.configuration_service import ConfigurationService
from iris.services.event_bus import EventBus
from iris.services.logger import get_logger
from iris.services.notification_manager import NotificationManager
from iris.services.plugin_loader import PluginLoader
from iris.services.process_manager import ProcessManager
from iris.services.secrets_manager import SecretsManager
from iris.services.service_registry import ServiceRegistry
from iris.services.storage_manager import StorageManager
from iris.services.task_queue import TaskQueue
from iris.plugins.context import PluginContext
from iris.utils.status import ServiceStatus
from iris.workflows.decision_engine import DecisionEngine
from iris.workflows.engine import WorkflowEngine
from iris.workflows.scheduler import SchedulerService


@dataclass(frozen=True)
class IrisStatus:
    """Snapshot of the IRIS runtime state."""

    status: ServiceStatus
    registered_agents: int
    queue_size: int
    running_tasks: int
    completed_tasks: int
    services: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Return the status snapshot as primitive values."""
        return {
            "status": self.status.value,
            "registered_agents": self.registered_agents,
            "queue_size": self.queue_size,
            "running_tasks": self.running_tasks,
            "completed_tasks": self.completed_tasks,
            "services": self.services,
        }


class IrisCore:
    """Coordinates IRIS platform startup, shutdown, and agent registration."""

    def __init__(
        self,
        agent_manager: AgentManager | None = None,
        event_bus: EventBus | None = None,
        task_queue: TaskQueue | None = None,
        async_runtime: AsyncRuntime | None = None,
        service_registry: ServiceRegistry | None = None,
    ) -> None:
        self._logger = get_logger(__name__)
        self._service_registry = service_registry or ServiceRegistry()
        self._service_registry.register("agent_manager", agent_manager or AgentManager())
        self._service_registry.register("event_bus", event_bus or EventBus())
        self._service_registry.register("task_queue", task_queue or TaskQueue())
        self._service_registry.register("async_runtime", async_runtime or AsyncRuntime())
        self._service_registry.register("configuration", ConfigurationService())
        self._service_registry.register("storage", StorageManager())
        self._service_registry.register("secrets", SecretsManager())
        self._service_registry.register("process_manager", ProcessManager())
        self._service_registry.register("notifications", NotificationManager())

        decision_engine = DecisionEngine()
        workflow_engine = WorkflowEngine(
            task_queue=self.task_queue,
            event_bus=self.event_bus,
            storage=self._service_registry.get("storage", StorageManager),
            decision_engine=decision_engine,
            configuration=self._service_registry.get("configuration", ConfigurationService),
        )
        scheduler = SchedulerService(
            workflow_engine=workflow_engine,
            storage=self._service_registry.get("storage", StorageManager),
            event_bus=self.event_bus,
        )
        self._service_registry.register("decision_engine", decision_engine)
        self._service_registry.register("workflow_engine", workflow_engine)
        self._service_registry.register("scheduler", scheduler)

        background_worker = BackgroundWorker(self.task_queue, self.event_bus)
        plugin_context = PluginContext(
            event_bus=self.event_bus,
            task_queue=self.task_queue,
            process_manager=self._service_registry.get("process_manager", ProcessManager),
            configuration=self._service_registry.get("configuration", ConfigurationService),
            service_registry=self._service_registry,
            logger=get_logger("iris.plugins"),
            workflow_engine=workflow_engine,
            scheduler=scheduler,
            decision_engine=decision_engine,
        )
        plugin_loader = PluginLoader(event_bus=self.event_bus, context=plugin_context)
        self._service_registry.register("background_worker", background_worker)
        self._service_registry.register("plugin_loader", plugin_loader)
        self._status = ServiceStatus.OFFLINE

    @property
    def status(self) -> ServiceStatus:
        """Return the current core status."""
        return self._status

    @property
    def service_registry(self) -> ServiceRegistry:
        """Return the platform service registry."""
        return self._service_registry

    @property
    def event_bus(self) -> EventBus:
        """Return the platform event bus."""
        return self._service_registry.get("event_bus", EventBus)

    @property
    def task_queue(self) -> TaskQueue:
        """Return the platform task queue."""
        return self._service_registry.get("task_queue", TaskQueue)

    def start(self) -> None:
        """Mark the IRIS core as online."""
        if self._status is ServiceStatus.ONLINE:
            self._logger.debug("IRIS core already online")
            return

        self._start_system_services()
        async_runtime = self._service_registry.get("async_runtime", AsyncRuntime)
        worker = self._service_registry.get("background_worker", BackgroundWorker)
        async_runtime.start()
        async_runtime.submit(worker.start()).result(timeout=5)
        self._register_discovered_plugins()
        self._status = ServiceStatus.ONLINE
        self._logger.info("IRIS core started")

    def stop(self) -> None:
        """Stop all registered agents and mark the IRIS core as offline."""
        if self._status is ServiceStatus.OFFLINE:
            self._logger.debug("IRIS core already offline")
            return

        agent_manager = self._service_registry.get("agent_manager", AgentManager)
        for agent in agent_manager.list_agents():
            agent.stop()

        async_runtime = self._service_registry.get("async_runtime", AsyncRuntime)
        worker = self._service_registry.get("background_worker", BackgroundWorker)
        async_runtime.submit(worker.stop()).result(timeout=5)
        async_runtime.stop()
        self._stop_system_services()
        self._status = ServiceStatus.OFFLINE
        self._logger.info("IRIS core stopped")

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the platform."""
        agent.attach_event_bus(self.event_bus)
        agent_manager = self._service_registry.get("agent_manager", AgentManager)
        agent_manager.register(agent)
        self._logger.info("Registered agent: {}", agent.name)

    def unregister_agent(self, name: str) -> None:
        """Unregister an agent by name."""
        agent_manager = self._service_registry.get("agent_manager", AgentManager)
        agent_manager.unregister(name)
        self._logger.info("Unregistered agent: {}", name)

    def get_status(self) -> IrisStatus:
        """Return a snapshot of the current platform status."""
        agent_manager = self._service_registry.get("agent_manager", AgentManager)
        return IrisStatus(
            status=self._status,
            registered_agents=len(agent_manager.list_agents()),
            queue_size=self.task_queue.queue_size(),
            running_tasks=self.task_queue.running_count(),
            completed_tasks=self.task_queue.completed_count(),
            services=[
                {
                    "name": service.name,
                    "status": service.status.value,
                    "healthy": service.healthy,
                    "version": service.version,
                }
                for service in self._service_registry.health_report(
                    [
                        "configuration",
                        "storage",
                        "secrets",
                        "process_manager",
                        "notifications",
                        "workflow_engine",
                        "scheduler",
                        "decision_engine",
                        "Service Registry",
                    ]
                )
            ],
        )

    def _register_discovered_plugins(self) -> None:
        """Register discovered plugin agents."""
        plugin_loader = self._service_registry.get("plugin_loader", PluginLoader)
        agent_manager = self._service_registry.get("agent_manager", AgentManager)
        for agent in plugin_loader.discover():
            if agent_manager.get_agent(agent.name) is not None:
                self._logger.warning("Skipping duplicate plugin agent: {}", agent.name)
                continue

            self.register_agent(agent)

    def _start_system_services(self) -> None:
        """Start registry-managed system services."""
        for name in (
            "Service Registry",
            "configuration",
            "storage",
            "secrets",
            "process_manager",
            "notifications",
        ):
            self._service_registry.get(name).start()
        self._service_registry.get("workflow_engine", WorkflowEngine).load_workflows()

    def _stop_system_services(self) -> None:
        """Stop registry-managed system services."""
        for name in (
            "notifications",
            "process_manager",
            "secrets",
            "storage",
            "configuration",
            "Service Registry",
        ):
            self._service_registry.get(name).stop()
