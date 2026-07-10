"""Dashboard presentation model for IRIS."""

from __future__ import annotations

from dataclasses import dataclass

from iris.core.iris_core import IrisCore
from iris.services.logger import LogBuffer
from iris.services.metrics import MetricsService, SystemMetrics


@dataclass(frozen=True)
class DashboardState:
    """State displayed by the dashboard."""

    iris_status: str
    registered_agents: int
    queue_size: int
    running_tasks: int
    completed_tasks: int
    metrics: SystemMetrics
    logs: list[str]


class DashboardViewModel:
    """Read-only adapter between UI widgets and infrastructure services."""

    def __init__(
        self,
        core: IrisCore,
        metrics_service: MetricsService,
        log_buffer: LogBuffer,
    ) -> None:
        self._core = core
        self._metrics_service = metrics_service
        self._log_buffer = log_buffer

    def snapshot(self) -> DashboardState:
        """Return the latest dashboard state."""
        status = self._core.get_status()
        return DashboardState(
            iris_status=status.status.value,
            registered_agents=status.registered_agents,
            queue_size=status.queue_size,
            running_tasks=status.running_tasks,
            completed_tasks=status.completed_tasks,
            metrics=self._metrics_service.snapshot(),
            logs=self._log_buffer.lines(),
        )
