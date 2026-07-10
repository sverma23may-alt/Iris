"""Workflow domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class ExecutionState(str, Enum):
    """Supported workflow execution states."""

    QUEUED = "Queued"
    RUNNING = "Running"
    PAUSED = "Paused"
    WAITING = "Waiting"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    RETRYING = "Retrying"


@dataclass(slots=True)
class WorkflowStep:
    """A single workflow step definition."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    max_retries: int = 0
    decision_rules: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_definition(cls, definition: str | dict[str, Any]) -> "WorkflowStep":
        """Create a workflow step from compact JSON definitions."""
        if isinstance(definition, str):
            return cls(name=definition)
        return cls(
            name=str(definition["name"]),
            payload=dict(definition.get("payload", {})),
            priority=int(definition.get("priority", 50)),
            max_retries=int(definition.get("max_retries", 0)),
            decision_rules=dict(definition.get("decision_rules", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "payload": self.payload,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "decision_rules": self.decision_rules,
        }


@dataclass(slots=True)
class Workflow:
    """Workflow definition loaded from JSON."""

    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create a workflow from a JSON-compatible dictionary."""
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            steps=[WorkflowStep.from_definition(step) for step in data.get("steps", [])],
            workflow_id=str(data.get("workflow_id") or uuid4()),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ExecutionContext:
    """Mutable data shared across workflow steps."""

    workflow_id: str
    execution_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    user_rules: dict[str, Any] = field(default_factory=dict)
    time_rules: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "variables": self.variables,
            "user_rules": self.user_rules,
            "time_rules": self.time_rules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionContext":
        """Create context from persisted data."""
        return cls(
            workflow_id=str(data["workflow_id"]),
            execution_id=str(data["execution_id"]),
            variables=dict(data.get("variables", {})),
            user_rules=dict(data.get("user_rules", {})),
            time_rules=dict(data.get("time_rules", {})),
        )


@dataclass(slots=True)
class WorkflowExecution:
    """Persisted workflow execution state."""

    workflow_id: str
    workflow_name: str
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: ExecutionState = ExecutionState.QUEUED
    errors: list[str] = field(default_factory=list)
    retry_count: int = 0
    context: ExecutionContext | None = None
    task_ids: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Return execution duration when start and finish times are known."""
        if self.started_at is None:
            return None
        end = self.finished_at or datetime.now(UTC)
        return max(0.0, (end - self.started_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "execution_id": self.execution_id,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "start_time": self.started_at.isoformat() if self.started_at else None,
            "finish_time": self.finished_at.isoformat() if self.finished_at else None,
            "duration": self.duration_seconds,
            "status": self.status.value,
            "errors": self.errors,
            "retry_count": self.retry_count,
            "context": self.context.to_dict() if self.context else None,
            "task_ids": self.task_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowExecution":
        """Create execution state from persisted data."""
        started_at = _parse_datetime(data.get("start_time"))
        finished_at = _parse_datetime(data.get("finish_time"))
        context_data = data.get("context")
        return cls(
            workflow_id=str(data["workflow_id"]),
            workflow_name=str(data["workflow_name"]),
            execution_id=str(data["execution_id"]),
            current_step=data.get("current_step"),
            completed_steps=list(data.get("completed_steps", [])),
            started_at=started_at,
            finished_at=finished_at,
            status=ExecutionState(data.get("status", ExecutionState.QUEUED.value)),
            errors=list(data.get("errors", [])),
            retry_count=int(data.get("retry_count", 0)),
            context=ExecutionContext.from_dict(context_data) if isinstance(context_data, dict) else None,
            task_ids=list(data.get("task_ids", [])),
        )


@dataclass(slots=True)
class WorkflowHistory:
    """Collection of workflow execution records."""

    executions: list[WorkflowExecution] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {"executions": [execution.to_dict() for execution in self.executions]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowHistory":
        """Create history from persisted data."""
        return cls(
            executions=[
                WorkflowExecution.from_dict(item)
                for item in data.get("executions", [])
                if isinstance(item, dict)
            ]
        )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
