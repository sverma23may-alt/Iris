"""Tests for Sprint 5 workflow orchestration."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from iris.services.background_worker import BackgroundWorker
from iris.services.configuration_service import ConfigurationService
from iris.services.event_bus import EventBus
from iris.services.storage_manager import StorageManager
from iris.services.task_queue import TaskQueue
from iris.workflows.decision_engine import DecisionEngine, DecisionInput, DecisionOutcome
from iris.workflows.engine import WorkflowEngine
from iris.workflows.models import ExecutionState
from iris.workflows.scheduler import ScheduleType, SchedulerService


class DecisionEngineTests(unittest.TestCase):
    """Decision engine behavior."""

    def test_decision_outputs_execute_skip_retry_delay_and_reject(self) -> None:
        engine = DecisionEngine()

        self.assertEqual(engine.decide(DecisionInput()).outcome, DecisionOutcome.EXECUTE)
        self.assertEqual(
            engine.decide(DecisionInput(duplicate_detected=True)).outcome,
            DecisionOutcome.SKIP,
        )
        self.assertEqual(
            engine.decide(
                DecisionInput(confidence=0.2, user_rules={"minimum_confidence": 0.8})
            ).outcome,
            DecisionOutcome.RETRY,
        )
        self.assertEqual(
            engine.decide(DecisionInput(time_rules={"delay_seconds": 5})).outcome,
            DecisionOutcome.DELAY,
        )
        self.assertEqual(
            engine.decide(DecisionInput(user_rules={"reject": True})).outcome,
            DecisionOutcome.REJECT,
        )


class WorkflowEngineTests(unittest.IsolatedAsyncioTestCase):
    """Workflow engine behavior."""

    async def test_executes_workflow_steps_through_task_queue(self) -> None:
        harness = _WorkflowHarness()
        workflow = harness.engine.create_workflow(
            {
                "name": "youtube_daily",
                "description": "Automatically generate and upload one video",
                "steps": ["research", "decision", "youtube"],
            }
        )
        executed: list[str] = []

        async def record_step(task) -> None:
            executed.append(task.payload["step"])

        for step in ("research", "decision", "youtube"):
            harness.engine.register_step_handler(step, record_step)

        execution_id = harness.engine.run(workflow.workflow_id)
        await harness.drain()

        execution = harness.engine.get_execution(execution_id)
        self.assertEqual(execution.status, ExecutionState.COMPLETED)
        self.assertEqual(executed, ["research", "decision", "youtube"])
        self.assertEqual(execution.completed_steps, executed)

    async def test_pause_resume_retry_and_cancel(self) -> None:
        harness = _WorkflowHarness()
        workflow = harness.engine.create_workflow({"name": "ops", "steps": ["one", "two"]})
        execution_id = harness.engine.run(workflow.workflow_id)

        harness.engine.pause(execution_id)
        self.assertEqual(harness.engine.get_execution(execution_id).status, ExecutionState.PAUSED)

        harness.engine.resume(execution_id)
        await harness.drain()
        self.assertEqual(harness.engine.get_execution(execution_id).status, ExecutionState.COMPLETED)

        failing = harness.engine.create_workflow({"name": "failure", "steps": ["fail"]})

        async def fail(_task) -> None:
            raise RuntimeError("boom")

        harness.engine.register_step_handler("fail", fail)
        failed_id = harness.engine.run(failing.workflow_id)
        await harness.drain(expected_completed=0)
        self.assertEqual(harness.engine.get_execution(failed_id).status, ExecutionState.FAILED)

        harness.engine.cancel(failed_id)
        self.assertEqual(harness.engine.get_execution(failed_id).status, ExecutionState.CANCELLED)
        harness.engine.retry(failed_id)
        self.assertEqual(harness.engine.get_execution(failed_id).retry_count, 1)

    async def test_persistence_resumes_waiting_execution_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = StorageManager(root_path=Path(directory))
            storage.start()
            engine = _make_engine(storage)
            workflow = engine.create_workflow({"name": "persisted", "steps": ["one"]})
            execution_id = engine.run(workflow.workflow_id)

            restarted = _make_engine(storage)
            restarted.load_workflows()

            self.assertIn(workflow.workflow_id, {item.workflow_id for item in restarted.list_workflows()})
            self.assertEqual(restarted.get_execution(execution_id).status, ExecutionState.WAITING)


class SchedulerServiceTests(unittest.TestCase):
    """Scheduler behavior."""

    def test_due_schedule_triggers_workflow_and_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = StorageManager(root_path=Path(directory))
            storage.start()
            event_bus = EventBus()
            engine = _make_engine(storage, event_bus=event_bus)
            workflow = engine.create_workflow({"name": "scheduled", "steps": ["one"]})
            scheduler = SchedulerService(engine, storage, event_bus)
            run_at = datetime.now(UTC) - timedelta(seconds=1)

            schedule = scheduler.schedule(
                workflow.workflow_id,
                ScheduleType.ONCE,
                run_at=run_at,
                timezone="UTC",
                recurring=False,
            )
            executions = scheduler.tick(datetime.now(UTC))

            self.assertEqual(len(executions), 1)
            self.assertFalse(scheduler.list_schedules()[0].enabled)
            reloaded = SchedulerService(engine, storage, event_bus)
            self.assertEqual(reloaded.list_schedules()[0].schedule_id, schedule.schedule_id)


class IrisCoreWorkflowIntegrationTests(unittest.TestCase):
    """Core workflow service registration."""

    def test_core_registers_workflow_services(self) -> None:
        from iris.core.iris_core import IrisCore
        from iris.workflows.scheduler import SchedulerService

        core = IrisCore()

        self.assertIsInstance(core.service_registry.get("workflow_engine", WorkflowEngine), WorkflowEngine)
        self.assertIsInstance(core.service_registry.get("scheduler", SchedulerService), SchedulerService)
        self.assertIsInstance(core.service_registry.get("decision_engine", DecisionEngine), DecisionEngine)


class _WorkflowHarness:
    def __init__(self) -> None:
        self.storage_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(root_path=Path(self.storage_dir.name))
        self.storage.start()
        self.event_bus = EventBus()
        self.task_queue = TaskQueue()
        self.engine = _make_engine(self.storage, self.task_queue, self.event_bus)

    async def drain(self, expected_completed: int | None = None) -> None:
        worker = BackgroundWorker(self.task_queue, self.event_bus, poll_interval_seconds=0.01)
        await worker.start()
        for _ in range(200):
            if expected_completed is not None:
                if self.task_queue.completed_count() == expected_completed:
                    break
            elif self.task_queue.queue_size() == 0 and self.task_queue.running_count() == 0:
                break
            await asyncio.sleep(0.02)
        await worker.stop()


def _make_engine(
    storage: StorageManager,
    task_queue: TaskQueue | None = None,
    event_bus: EventBus | None = None,
) -> WorkflowEngine:
    return WorkflowEngine(
        task_queue=task_queue or TaskQueue(),
        event_bus=event_bus or EventBus(),
        storage=storage,
        decision_engine=DecisionEngine(),
        configuration=ConfigurationService(),
    )


if __name__ == "__main__":
    unittest.main()
