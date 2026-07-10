"""Workflow execution engine."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from iris.services.configuration_service import ConfigurationService
from iris.services.event_bus import Event, EventBus
from iris.services.storage_manager import StorageManager
from iris.services.task_queue import QueuedTask, TaskQueue
from iris.workflows.decision_engine import DecisionEngine, DecisionInput, DecisionOutcome
from iris.workflows.models import ExecutionContext, ExecutionState, Workflow, WorkflowExecution


StepHandler = Callable[[QueuedTask], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class WorkflowMetrics:
    """Aggregate workflow metrics."""

    workflow_count: int
    success_rate: float
    failure_rate: float
    average_duration: float
    average_retries: float
    scheduler_latency: float
    queue_wait_time: float

    def to_dict(self) -> dict[str, float | int]:
        """Return primitive dashboard data."""
        return {
            "workflow_count": self.workflow_count,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "average_duration": self.average_duration,
            "average_retries": self.average_retries,
            "scheduler_latency": self.scheduler_latency,
            "queue_wait_time": self.queue_wait_time,
        }


class WorkflowEngine:
    """Coordinate workflow definitions through the decision engine and task queue."""

    name = "Workflow Engine"
    version = "1.0.0"

    def __init__(
        self,
        task_queue: TaskQueue,
        event_bus: EventBus,
        storage: StorageManager,
        decision_engine: DecisionEngine,
        configuration: ConfigurationService,
    ) -> None:
        self._task_queue = task_queue
        self._event_bus = event_bus
        self._storage = storage
        self._decision_engine = decision_engine
        self._configuration = configuration
        self._workflows: dict[str, Workflow] = {}
        self._executions: dict[str, WorkflowExecution] = {}
        self._step_handlers: dict[str, StepHandler] = {}
        self._scheduler_latencies: list[float] = []
        self._queue_wait_times: list[float] = []

    def create_workflow(self, definition: dict[str, Any] | Workflow) -> Workflow:
        """Register and persist a workflow definition."""
        workflow = definition if isinstance(definition, Workflow) else Workflow.from_dict(definition)
        self._workflows[workflow.workflow_id] = workflow
        self._persist_workflows()
        self._publish_now("workflow.created", {"workflow": workflow.to_dict()})
        return workflow

    def load_workflows(self) -> list[Workflow]:
        """Load persisted workflow definitions and executions."""
        workflow_data = self._storage.load_json("workflows", "definitions.json", {"workflows": []})
        self._workflows = {
            workflow.workflow_id: workflow
            for workflow in (
                Workflow.from_dict(item)
                for item in workflow_data.get("workflows", [])
                if isinstance(item, dict)
            )
        }
        self.resume_from_storage()
        return self.list_workflows()

    def list_workflows(self) -> list[Workflow]:
        """Return registered workflows."""
        return list(self._workflows.values())

    def list_executions(self) -> list[WorkflowExecution]:
        """Return known workflow executions."""
        return list(self._executions.values())

    def get_execution(self, execution_id: str) -> WorkflowExecution:
        """Return an execution by id."""
        return self._executions[execution_id]

    def register_step_handler(self, step_name: str, handler: StepHandler) -> None:
        """Register a generic task-queue handler for a step name."""
        self._step_handlers[step_name] = handler

    def run(
        self,
        workflow_id: str,
        variables: dict[str, Any] | None = None,
        user_rules: dict[str, Any] | None = None,
        time_rules: dict[str, Any] | None = None,
    ) -> str:
        """Manually start a workflow execution."""
        workflow = self._workflows[workflow_id]
        execution = WorkflowExecution(workflow_id=workflow.workflow_id, workflow_name=workflow.name)
        execution.context = ExecutionContext(
            workflow_id=workflow.workflow_id,
            execution_id=execution.execution_id,
            variables=variables or {},
            user_rules=user_rules or {},
            time_rules=time_rules or {},
        )
        self._executions[execution.execution_id] = execution
        self._persist_executions()
        self._queue_next_step(workflow, execution)
        return execution.execution_id

    def pause(self, execution_id: str) -> None:
        """Pause a queued or running workflow."""
        execution = self._executions[execution_id]
        execution.status = ExecutionState.PAUSED
        self._persist_executions()
        self._publish_now("workflow.paused", {"execution_id": execution_id})

    def resume(self, execution_id: str) -> None:
        """Resume a paused or waiting workflow."""
        execution = self._executions[execution_id]
        workflow = self._workflows[execution.workflow_id]
        execution.status = ExecutionState.WAITING
        self._persist_executions()
        self._publish_now("workflow.resumed", {"execution_id": execution_id})
        self._queue_next_step(workflow, execution)

    def retry(self, execution_id: str) -> None:
        """Retry a failed workflow from its current step."""
        execution = self._executions[execution_id]
        execution.retry_count += 1
        execution.status = ExecutionState.RETRYING
        self._persist_executions()
        self._publish_now("workflow.step.started", {"execution_id": execution_id, "retry": True})
        self.resume(execution_id)

    def cancel(self, execution_id: str) -> None:
        """Cancel a workflow and any queued tasks owned by it."""
        execution = self._executions[execution_id]
        execution.status = ExecutionState.CANCELLED
        execution.finished_at = datetime.now(UTC)
        for task_id in execution.task_ids:
            try:
                self._task_queue.cancel_task(task_id)
            except KeyError:
                continue
        self._persist_executions()
        self._publish_now("workflow.cancelled", {"execution_id": execution_id})

    def resume_from_storage(self) -> None:
        """Reload persisted executions so workflows can survive restarts."""
        data = self._storage.load_json("workflows", "executions.json", {"executions": []})
        self._executions = {
            execution.execution_id: execution
            for execution in (
                WorkflowExecution.from_dict(item)
                for item in data.get("executions", [])
                if isinstance(item, dict)
            )
        }
        for execution in self._executions.values():
            if execution.status in {
                ExecutionState.QUEUED,
                ExecutionState.RUNNING,
                ExecutionState.WAITING,
                ExecutionState.RETRYING,
            }:
                execution.status = ExecutionState.WAITING

    def record_scheduler_latency(self, latency_seconds: float) -> None:
        """Track scheduler trigger latency."""
        self._scheduler_latencies.append(max(0.0, latency_seconds))

    def metrics(self) -> WorkflowMetrics:
        """Return aggregate workflow metrics."""
        executions = list(self._executions.values())
        completed = [item for item in executions if item.status is ExecutionState.COMPLETED]
        failed = [item for item in executions if item.status is ExecutionState.FAILED]
        durations = [item.duration_seconds or 0.0 for item in completed]
        retries = [item.retry_count for item in executions]
        total = len(executions)
        return WorkflowMetrics(
            workflow_count=len(self._workflows),
            success_rate=(len(completed) / total) if total else 0.0,
            failure_rate=(len(failed) / total) if total else 0.0,
            average_duration=(sum(durations) / len(durations)) if durations else 0.0,
            average_retries=(sum(retries) / len(retries)) if retries else 0.0,
            scheduler_latency=self._average(self._scheduler_latencies),
            queue_wait_time=self._average(self._queue_wait_times),
        )

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Return dashboard-ready workflow state."""
        executions = [execution.to_dict() for execution in self.list_executions()]
        return {
            "workflows": [workflow.to_dict() for workflow in self.list_workflows()],
            "executions": executions,
            "running": [item for item in executions if item["status"] == ExecutionState.RUNNING.value],
            "queued": [item for item in executions if item["status"] == ExecutionState.QUEUED.value],
            "completed": [item for item in executions if item["status"] == ExecutionState.COMPLETED.value],
            "failed": [item for item in executions if item["status"] == ExecutionState.FAILED.value],
            "metrics": self.metrics().to_dict(),
        }

    def _queue_next_step(self, workflow: Workflow, execution: WorkflowExecution) -> None:
        if execution.status is ExecutionState.PAUSED:
            return

        if execution.started_at is None:
            execution.started_at = datetime.now(UTC)
            self._publish_now("workflow.started", {"execution_id": execution.execution_id})

        next_step = self._next_step(workflow, execution)
        if next_step is None:
            execution.status = ExecutionState.COMPLETED
            execution.finished_at = datetime.now(UTC)
            self._persist_executions()
            self._publish_now("workflow.completed", {"execution_id": execution.execution_id})
            return

        decision = self._decision_for(execution, next_step.decision_rules)
        self._publish_now(
            "decision.made",
            {
                "execution_id": execution.execution_id,
                "step": next_step.name,
                "decision": decision.to_dict(),
            },
        )

        if decision.outcome is DecisionOutcome.SKIP:
            execution.completed_steps.append(next_step.name)
            self._persist_executions()
            self._queue_next_step(workflow, execution)
            return

        if decision.outcome is DecisionOutcome.REJECT:
            execution.status = ExecutionState.FAILED
            execution.errors.extend(decision.reasons)
            execution.finished_at = datetime.now(UTC)
            self._persist_executions()
            self._publish_now("workflow.failed", {"execution_id": execution.execution_id, "errors": execution.errors})
            return

        if decision.outcome is DecisionOutcome.DELAY:
            execution.status = ExecutionState.WAITING
            self._persist_executions()
            return

        execution.current_step = next_step.name
        execution.status = ExecutionState.QUEUED
        queued_at = datetime.now(UTC)

        task = QueuedTask(
            name=f"workflow.{workflow.name}.{next_step.name}",
            handler=lambda queued_task: self._execute_step_task(
                queued_task, workflow.workflow_id, execution.execution_id, next_step.name, queued_at
            ),
            payload={
                **next_step.payload,
                "workflow_id": workflow.workflow_id,
                "execution_id": execution.execution_id,
                "step": next_step.name,
            },
            priority=next_step.priority,
            max_retries=next_step.max_retries,
        )
        execution.task_ids.append(self._task_queue.add_task(task))
        self._persist_executions()

    async def _execute_step_task(
        self,
        task: QueuedTask,
        workflow_id: str,
        execution_id: str,
        step_name: str,
        queued_at: datetime,
    ) -> None:
        execution = self._executions[execution_id]
        workflow = self._workflows[workflow_id]
        if step_name in execution.completed_steps:
            return
        if execution.status is ExecutionState.CANCELLED:
            return
        if execution.status is ExecutionState.PAUSED:
            execution.status = ExecutionState.WAITING
            self._persist_executions()
            return

        self._queue_wait_times.append((datetime.now(UTC) - queued_at).total_seconds())
        execution.status = ExecutionState.RUNNING
        self._persist_executions()
        await self._event_bus.publish(Event("workflow.step.started", {"execution_id": execution_id, "step": step_name}, source=self.name))

        try:
            handler = self._step_handlers.get(step_name, self._default_step_handler(step_name))
            result = handler(task)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            execution.status = ExecutionState.FAILED
            execution.errors.append(str(exc))
            execution.finished_at = datetime.now(UTC)
            self._persist_executions()
            await self._event_bus.publish(Event("workflow.failed", {"execution_id": execution_id, "error": str(exc)}, source=self.name))
            raise

        execution.completed_steps.append(step_name)
        await self._event_bus.publish(Event("workflow.step.completed", {"execution_id": execution_id, "step": step_name}, source=self.name))
        self._queue_next_step(workflow, execution)

    def _default_step_handler(self, step_name: str) -> StepHandler:
        async def publish_configured_event(task: QueuedTask) -> None:
            step_events = self._configuration.get("workflow.step_events", {}) or {}
            event_name = step_events.get(step_name, f"workflow.step.{step_name}.requested")
            await self._event_bus.publish(Event(event_name, task.payload, source=self.name))

        return publish_configured_event

    def _next_step(self, workflow: Workflow, execution: WorkflowExecution) -> Any | None:
        completed = set(execution.completed_steps)
        for step in workflow.steps:
            if step.name not in completed:
                return step
        return None

    def _decision_for(self, execution: WorkflowExecution, step_rules: dict[str, Any]) -> Any:
        context = execution.context or ExecutionContext(execution.workflow_id, execution.execution_id)
        variables = context.variables
        user_rules = {**context.user_rules, **step_rules}
        return self._decision_engine.decide(
            DecisionInput(
                research_score=_optional_float(variables.get("research_score")),
                confidence=_optional_float(variables.get("confidence")),
                duplicate_detected=bool(variables.get("duplicate_detected", False)),
                category=str(variables["category"]) if variables.get("category") is not None else None,
                user_rules=user_rules,
                time_rules=context.time_rules,
                retry_count=execution.retry_count,
            )
        )

    def _persist_workflows(self) -> None:
        self._storage.save_json(
            "workflows",
            "definitions.json",
            {"workflows": [workflow.to_dict() for workflow in self._workflows.values()]},
        )

    def _persist_executions(self) -> None:
        self._storage.save_json(
            "workflows",
            "executions.json",
            {"executions": [execution.to_dict() for execution in self._executions.values()]},
        )

    def _publish_now(self, event_name: str, payload: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._event_bus.publish(Event(event_name, payload, source=self.name)))
            return
        loop.create_task(self._event_bus.publish(Event(event_name, payload, source=self.name)))

    @staticmethod
    def _average(values: list[float]) -> float:
        return (sum(values) / len(values)) if values else 0.0


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
