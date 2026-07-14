"""IRIS Vision presentation model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from iris.ai_router.exceptions import ProviderExecutionError, ProviderUnavailableError
from iris.ai_router.router import AIRouter
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
    ai_router: dict[str, Any]
    workflows: dict[str, Any]
    scheduler: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    """A single turn in the IRIS Chat conversation."""

    role: str
    text: str
    timestamp: str
    provider: str | None = None
    latency_ms: float | None = None


@dataclass(frozen=True)
class ChatResult:
    """Outcome of requesting an assistant reply from the AI Router."""

    message: ChatMessage
    used_fallback: bool
    notice: str | None = None


class DashboardViewModel:
    """Adapter between IRIS Vision widgets and infrastructure services."""

    def __init__(
        self,
        core: IrisCore,
        metrics_service: MetricsService,
        log_buffer: LogBuffer,
    ) -> None:
        self._core = core
        self._metrics_service = metrics_service
        self._log_buffer = log_buffer
        self._chat_history: list[ChatMessage] = []

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
            ai_router=self._ai_router_snapshot(),
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

    def chat_history(self) -> list[ChatMessage]:
        """Return the IRIS Chat conversation so far."""
        return list(self._chat_history)

    def append_user_message(self, text: str) -> ChatMessage:
        """Record a user chat message. Safe to call from the UI thread."""
        message = ChatMessage(role="user", text=text, timestamp=_now_display_time())
        self._chat_history.append(message)
        return message

    def request_assistant_reply(self) -> ChatResult:
        """Send the conversation to AIRouter and append the assistant's reply.

        Prefers Gemini; automatically falls back to MockProvider when Gemini is
        unavailable or a request fails, per the existing AIRouter fallback
        behavior. Never raises - always returns a ChatResult so the UI thread
        never crashes, even if no provider could be reached at all. Safe to
        call from a background thread; only reads/appends to the in-memory
        chat history list.
        """
        router = self._ai_router()
        if router is None:
            message = ChatMessage(
                role="assistant",
                text="IRIS could not reach the AI Router.",
                timestamp=_now_display_time(),
            )
            self._chat_history.append(message)
            return ChatResult(message=message, used_fallback=False, notice="AI Router is unavailable.")

        payload = [
            {"role": entry.role, "content": entry.text}
            for entry in self._chat_history
            if entry.role in ("user", "assistant")
        ]

        used_fallback = False
        try:
            response = router.chat(payload, provider_name="gemini")
        except (ProviderUnavailableError, ProviderExecutionError):
            # select_provider() raises before AIRouter's own internal fallback
            # logic ever runs (that only kicks in once a provider has been
            # selected and its request fails), so an outright-unavailable
            # Gemini needs an explicit retry against Mock here.
            used_fallback = True
            try:
                response = router.chat(payload, provider_name="mock")
            except (ProviderUnavailableError, ProviderExecutionError) as exc:
                message = ChatMessage(
                    role="assistant",
                    text="IRIS could not reach any AI provider right now. Please try again shortly.",
                    timestamp=_now_display_time(),
                )
                self._chat_history.append(message)
                return ChatResult(message=message, used_fallback=True, notice=str(exc))
        else:
            # AIRouter._fallback_or_error() already retries against the
            # configured fallback_provider internally when Gemini's request
            # itself fails, returning a successful response without raising.
            # Detect that silent substitution from the response instead.
            used_fallback = response.provider != "gemini"

        message = ChatMessage(
            role="assistant",
            text=str(response.response),
            timestamp=_now_display_time(),
            provider=response.provider,
            latency_ms=response.latency_ms,
        )
        self._chat_history.append(message)
        notice = "Gemini unavailable. Using Mock Provider." if used_fallback else None
        return ChatResult(message=message, used_fallback=used_fallback, notice=notice)

    def clear_chat(self) -> None:
        """Clear the IRIS Chat conversation history."""
        self._chat_history.clear()

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

    def _ai_router_snapshot(self) -> dict[str, Any]:
        router = self._ai_router()
        if router is None:
            return {
                "registered_providers": [],
                "provider_status": [],
                "routing_mode": "unavailable",
                "current_provider": None,
                "configuration": {},
            }
        return router.dashboard_snapshot()

    def _ai_router(self) -> AIRouter | None:
        try:
            return self._core.service_registry.get("ai_router", AIRouter)
        except KeyError:
            return None

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


def _now_display_time() -> str:
    """Return a short local time string for chat message badges."""
    return datetime.now().strftime("%H:%M:%S")
