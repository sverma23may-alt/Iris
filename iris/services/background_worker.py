"""Asynchronous background worker for queued tasks."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from iris.services.event_bus import Event, EventBus
from iris.services.logger import get_logger
from iris.services.task_queue import QueuedTask, TaskQueue


class BackgroundWorker:
    """Non-blocking async worker that executes tasks from a queue."""

    def __init__(
        self,
        task_queue: TaskQueue,
        event_bus: EventBus,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._logger = get_logger(__name__)
        self._task_queue = task_queue
        self._event_bus = event_bus
        self._poll_interval_seconds = poll_interval_seconds
        self._running = False
        self._worker_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Return True when the worker loop is active."""
        return self._running

    async def start(self) -> None:
        """Start the worker loop without blocking the caller."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._run())
        self._logger.info("Background worker started")

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task
        self._logger.info("Background worker stopped")

    async def _run(self) -> None:
        while self._running:
            task = self._task_queue.get_next_task()
            if task is None:
                await asyncio.sleep(self._poll_interval_seconds)
                continue

            await self._execute(task)

    async def _execute(self, task: QueuedTask) -> None:
        await self._event_bus.publish(
            Event("task.started", {"task_id": task.task_id, "name": task.name}, source="worker")
        )

        try:
            result = task.handler(task)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # pragma: no cover - defensive infrastructure boundary
            retrying = self._task_queue.mark_failed(task.task_id, str(exc))
            event_name = "task.retrying" if retrying else "task.failed"
            await self._event_bus.publish(
                Event(event_name, {"task_id": task.task_id, "error": str(exc)}, source="worker")
            )
            self._logger.exception("Task failed: {}", task.task_id)
            return

        self._task_queue.mark_completed(task.task_id)
        await self._event_bus.publish(
            Event("task.completed", {"task_id": task.task_id, "name": task.name}, source="worker")
        )
