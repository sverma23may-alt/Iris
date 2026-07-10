"""Persistent workflow scheduler service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from iris.services.event_bus import Event, EventBus
from iris.services.storage_manager import StorageManager
from iris.workflows.engine import WorkflowEngine


class ScheduleType(str, Enum):
    """Supported scheduler modes."""

    MANUAL = "manual"
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"
    DELAYED = "delayed"


@dataclass(slots=True)
class ScheduledWorkflow:
    """Persisted workflow schedule."""

    workflow_id: str
    schedule_type: ScheduleType
    schedule_id: str = field(default_factory=lambda: str(uuid4()))
    next_run_at: datetime | None = None
    timezone: str = "UTC"
    cron_expression: str | None = None
    recurring: bool = True
    enabled: bool = True
    last_execution_id: str | None = None
    last_run_at: datetime | None = None
    variables: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible scheduler data."""
        return {
            "schedule_id": self.schedule_id,
            "workflow_id": self.workflow_id,
            "schedule_type": self.schedule_type.value,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "timezone": self.timezone,
            "cron_expression": self.cron_expression,
            "recurring": self.recurring,
            "enabled": self.enabled,
            "last_execution_id": self.last_execution_id,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "variables": self.variables,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledWorkflow":
        """Load a persisted schedule."""
        return cls(
            workflow_id=str(data["workflow_id"]),
            schedule_type=ScheduleType(data["schedule_type"]),
            schedule_id=str(data.get("schedule_id") or uuid4()),
            next_run_at=_parse_datetime(data.get("next_run_at")),
            timezone=str(data.get("timezone", "UTC")),
            cron_expression=data.get("cron_expression"),
            recurring=bool(data.get("recurring", True)),
            enabled=bool(data.get("enabled", True)),
            last_execution_id=data.get("last_execution_id"),
            last_run_at=_parse_datetime(data.get("last_run_at")),
            variables=dict(data.get("variables", {})),
        )


class SchedulerService:
    """Workflow scheduler that persists schedules across restarts."""

    name = "Scheduler Service"
    version = "1.0.0"

    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        storage: StorageManager,
        event_bus: EventBus,
    ) -> None:
        self._workflow_engine = workflow_engine
        self._storage = storage
        self._event_bus = event_bus
        self._schedules: dict[str, ScheduledWorkflow] = {}
        self.load()

    def schedule(
        self,
        workflow_id: str,
        schedule_type: ScheduleType,
        run_at: datetime | None = None,
        timezone: str = "UTC",
        cron_expression: str | None = None,
        recurring: bool = True,
        variables: dict[str, Any] | None = None,
    ) -> ScheduledWorkflow:
        """Create or persist a workflow schedule."""
        schedule = ScheduledWorkflow(
            workflow_id=workflow_id,
            schedule_type=schedule_type,
            next_run_at=run_at,
            timezone=timezone,
            cron_expression=cron_expression,
            recurring=recurring,
            variables=variables or {},
        )
        if schedule.next_run_at is None and schedule_type is ScheduleType.DELAYED:
            schedule.next_run_at = datetime.now(UTC) + timedelta(seconds=1)
        self._schedules[schedule.schedule_id] = schedule
        self.save()
        return schedule

    def manual(self, workflow_id: str, variables: dict[str, Any] | None = None) -> str:
        """Run a workflow manually."""
        return self._workflow_engine.run(workflow_id, variables=variables)

    def tick(self, now: datetime | None = None) -> list[str]:
        """Trigger all due schedules and return execution ids."""
        current = now or datetime.now(UTC)
        execution_ids: list[str] = []
        self._publish_now("scheduler.started", {"checked_at": current.isoformat()})
        for schedule in list(self._schedules.values()):
            if not schedule.enabled or schedule.next_run_at is None:
                continue
            due_at = _aware(schedule.next_run_at, schedule.timezone)
            if due_at > current:
                continue

            latency = (current - due_at).total_seconds()
            self._workflow_engine.record_scheduler_latency(latency)
            execution_id = self._workflow_engine.run(schedule.workflow_id, variables=schedule.variables)
            schedule.last_execution_id = execution_id
            schedule.last_run_at = current
            execution_ids.append(execution_id)
            self._publish_now(
                "scheduler.triggered",
                {
                    "schedule_id": schedule.schedule_id,
                    "workflow_id": schedule.workflow_id,
                    "execution_id": execution_id,
                },
            )
            self._advance(schedule, current)
            self._publish_now("scheduler.completed", {"schedule_id": schedule.schedule_id})
        self.save()
        return execution_ids

    def list_schedules(self) -> list[ScheduledWorkflow]:
        """Return all schedules."""
        return list(self._schedules.values())

    def cancel(self, schedule_id: str) -> None:
        """Disable a schedule."""
        self._schedules[schedule_id].enabled = False
        self.save()

    def load(self) -> None:
        """Load schedules from storage."""
        data = self._storage.load_json("workflows", "schedules.json", {"schedules": []})
        self._schedules = {
            schedule.schedule_id: schedule
            for schedule in (
                ScheduledWorkflow.from_dict(item)
                for item in data.get("schedules", [])
                if isinstance(item, dict)
            )
        }

    def save(self) -> None:
        """Persist schedules."""
        self._storage.save_json(
            "workflows",
            "schedules.json",
            {"schedules": [schedule.to_dict() for schedule in self._schedules.values()]},
        )

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Return dashboard-ready scheduler data."""
        schedules = [schedule.to_dict() for schedule in self.list_schedules()]
        return {
            "schedules": schedules,
            "upcoming": [item for item in schedules if item["enabled"] and item["next_run_at"]],
        }

    def _advance(self, schedule: ScheduledWorkflow, now: datetime) -> None:
        if schedule.schedule_type in {ScheduleType.ONCE, ScheduleType.MANUAL, ScheduleType.DELAYED}:
            schedule.enabled = False
            return
        if not schedule.recurring:
            schedule.enabled = False
            return

        if schedule.schedule_type is ScheduleType.DAILY:
            schedule.next_run_at = now + timedelta(days=1)
        elif schedule.schedule_type is ScheduleType.WEEKLY:
            schedule.next_run_at = now + timedelta(weeks=1)
        elif schedule.schedule_type is ScheduleType.MONTHLY:
            schedule.next_run_at = now + timedelta(days=31)
        elif schedule.schedule_type is ScheduleType.CRON:
            schedule.next_run_at = _next_cron_run(schedule.cron_expression, now)

    def _publish_now(self, event_name: str, payload: dict[str, Any]) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._event_bus.publish(Event(event_name, payload, source=self.name)))
            return
        loop.create_task(self._event_bus.publish(Event(event_name, payload, source=self.name)))


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _aware(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    return value.replace(tzinfo=ZoneInfo(timezone)).astimezone(UTC)


def _next_cron_run(expression: str | None, now: datetime) -> datetime:
    if not expression:
        return now + timedelta(minutes=1)
    parts = expression.split()
    if len(parts) != 5:
        return now + timedelta(minutes=1)
    minute = parts[0]
    if minute.startswith("*/"):
        interval = max(1, int(minute[2:]))
        return now + timedelta(minutes=interval)
    if minute.isdigit():
        target = now.replace(minute=int(minute), second=0, microsecond=0)
        if target <= now:
            target += timedelta(hours=1)
        return target
    return now + timedelta(minutes=1)
