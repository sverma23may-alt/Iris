"""Dashboard presentation model for IRIS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.agents.manager import AgentManager
from iris.core.iris_core import IrisCore
from iris.services.logger import LogBuffer
from iris.services.metrics import MetricsService, SystemMetrics
from iris.workflows.engine import WorkflowEngine
from iris.workflows.scheduler import SchedulerService


@dataclass(frozen=True)
class DashboardState:
    """State displayed by the dashboard."""

    iris_status: str
    registered_agents: int
    queue_size: int
    running_tasks: int
    completed_tasks: int
    services: list[dict[str, object]]
    metrics: SystemMetrics
    logs: list[str]
    youtube_agent: dict[str, Any]
    research_agent: dict[str, Any]
    workflows: dict[str, Any]
    scheduler: dict[str, Any]


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
            services=status.services,
            metrics=self._metrics_service.snapshot(),
            logs=self._log_buffer.lines(),
            youtube_agent=self._youtube_agent_snapshot(),
            research_agent=self._research_agent_snapshot(),
            workflows=self._workflow_snapshot(),
            scheduler=self._scheduler_snapshot(),
        )

    def request_research_scan(self) -> str | None:
        """Queue a Research Agent scan from the dashboard."""
        agent = self._agent("Research Agent")
        if agent is None or not hasattr(agent, "submit_scan"):
            return None
        task_id = agent.submit_scan()
        if isinstance(task_id, str):
            return task_id
        return None

    def request_research_stop(self) -> None:
        """Request the Research Agent to stop the active scan."""
        agent = self._agent("Research Agent")
        if agent is not None and hasattr(agent, "request_stop"):
            agent.request_stop()

    def run_workflow(self, workflow_id: str) -> str | None:
        """Run a workflow by id."""
        engine = self._workflow_engine()
        if engine is None:
            return None
        return engine.run(workflow_id)

    def pause_workflow(self, execution_id: str) -> None:
        """Pause a workflow execution."""
        engine = self._workflow_engine()
        if engine is not None:
            engine.pause(execution_id)

    def resume_workflow(self, execution_id: str) -> None:
        """Resume a workflow execution."""
        engine = self._workflow_engine()
        if engine is not None:
            engine.resume(execution_id)

    def retry_workflow(self, execution_id: str) -> None:
        """Retry a workflow execution."""
        engine = self._workflow_engine()
        if engine is not None:
            engine.retry(execution_id)

    def cancel_workflow(self, execution_id: str) -> None:
        """Cancel a workflow execution."""
        engine = self._workflow_engine()
        if engine is not None:
            engine.cancel(execution_id)

    def _youtube_agent_snapshot(self) -> dict[str, Any]:
        agent = self._agent("YouTube Agent")
        if agent is None or not hasattr(agent, "dashboard_snapshot"):
            return {
                "status": "Unavailable",
                "current_task": "--",
                "clip_pilot_process_state": "--",
                "render_progress": 0,
                "upload_progress": 0,
                "recent_events": [],
                "last_generated_video": "--",
                "last_upload_url": "--",
            }

        snapshot = agent.dashboard_snapshot()
        if isinstance(snapshot, dict):
            return snapshot
        return {}

    def _research_agent_snapshot(self) -> dict[str, Any]:
        agent = self._agent("Research Agent")
        if agent is None or not hasattr(agent, "dashboard_snapshot"):
            return {
                "status": "Unavailable",
                "providers": [],
                "current_scan": "--",
                "topics_found": 0,
                "top_ranked_topics": [],
                "provider_status": [],
                "last_scan": "--",
                "recent_events": [],
            }

        snapshot = agent.dashboard_snapshot()
        if isinstance(snapshot, dict):
            return snapshot
        return {}

    def _workflow_snapshot(self) -> dict[str, Any]:
        engine = self._workflow_engine()
        if engine is None:
            return {
                "workflows": [],
                "executions": [],
                "running": [],
                "queued": [],
                "completed": [],
                "failed": [],
                "metrics": {},
            }
        return engine.dashboard_snapshot()

    def _scheduler_snapshot(self) -> dict[str, Any]:
        try:
            scheduler = self._core.service_registry.get("scheduler", SchedulerService)
        except KeyError:
            return {"schedules": [], "upcoming": []}
        return scheduler.dashboard_snapshot()

    def _workflow_engine(self) -> WorkflowEngine | None:
        try:
            return self._core.service_registry.get("workflow_engine", WorkflowEngine)
        except KeyError:
            return None

    def _agent(self, name: str) -> Any | None:
        agent_manager = self._core.service_registry.get("agent_manager", AgentManager)
        return agent_manager.get_agent(name)
