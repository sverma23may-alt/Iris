"""Stable dependency boundary for IRIS plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.services.configuration_service import ConfigurationService
from iris.services.event_bus import EventBus
from iris.services.process_manager import ProcessManager
from iris.services.service_registry import ServiceRegistry
from iris.services.task_queue import TaskQueue
from iris.workflows.decision_engine import DecisionEngine
from iris.workflows.engine import WorkflowEngine
from iris.workflows.scheduler import SchedulerService


@dataclass(frozen=True)
class PluginContext:
    """Production dependencies exposed to plugins through stable interfaces."""

    event_bus: EventBus
    task_queue: TaskQueue
    process_manager: ProcessManager
    configuration: ConfigurationService
    service_registry: ServiceRegistry
    logger: Any
    workflow_engine: WorkflowEngine | None = None
    scheduler: SchedulerService | None = None
    decision_engine: DecisionEngine | None = None
