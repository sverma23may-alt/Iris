"""Task queue infrastructure for IRIS."""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from threading import Lock
from typing import Any
from uuid import uuid4


TaskHandler = Callable[["QueuedTask"], None | Awaitable[None]]


class QueueMode(str, Enum):
    """Supported queue ordering strategies."""

    FIFO = "fifo"
    PRIORITY = "priority"


class TaskStatus(str, Enum):
    """Queued task lifecycle status."""

    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass(slots=True)
class QueuedTask:
    """Unit of work managed by the IRIS task queue."""

    name: str
    handler: TaskHandler
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    max_retries: int = 3
    task_id: str = field(default_factory=lambda: str(uuid4()))
    attempts: int = 0
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None

    def mark(self, status: TaskStatus) -> None:
        """Update task status and timestamp."""
        self.status = status
        self.updated_at = datetime.now(UTC)


class TaskQueue:
    """Thread-safe FIFO and priority task queue."""

    def __init__(self, mode: QueueMode = QueueMode.FIFO) -> None:
        self._mode = mode
        self._fifo: deque[str] = deque()
        self._priority: list[tuple[int, int, str]] = []
        self._tasks: dict[str, QueuedTask] = {}
        self._sequence = 0
        self._completed = 0
        self._running = 0
        self._lock = Lock()

    @property
    def mode(self) -> QueueMode:
        """Return the active queue mode."""
        return self._mode

    def add_task(self, task: QueuedTask) -> str:
        """Add a task to the queue and return its id."""
        with self._lock:
            self._tasks[task.task_id] = task
            self._enqueue(task)
            return task.task_id

    def remove_task(self, task_id: str) -> QueuedTask:
        """Remove a task from the queue by id."""
        with self._lock:
            task = self._tasks.pop(task_id)
            task.mark(TaskStatus.CANCELLED)
            return task

    def retry_task(self, task_id: str) -> None:
        """Retry a failed or cancelled task."""
        with self._lock:
            task = self._tasks[task_id]
            task.last_error = None
            task.mark(TaskStatus.PENDING)
            self._enqueue(task)

    def cancel_task(self, task_id: str) -> None:
        """Cancel a queued task."""
        with self._lock:
            task = self._tasks[task_id]
            task.mark(TaskStatus.CANCELLED)

    def get_next_task(self) -> QueuedTask | None:
        """Return the next pending task according to the active queue mode."""
        with self._lock:
            while True:
                task_id = self._pop_next_id()
                if task_id is None:
                    return None

                task = self._tasks.get(task_id)
                if task is None or task.status is not TaskStatus.PENDING:
                    continue

                task.attempts += 1
                task.mark(TaskStatus.RUNNING)
                self._running += 1
                return task

    def mark_completed(self, task_id: str) -> None:
        """Mark a task as completed."""
        with self._lock:
            task = self._tasks[task_id]
            task.mark(TaskStatus.COMPLETED)
            self._running = max(0, self._running - 1)
            self._completed += 1

    def mark_failed(self, task_id: str, error: str) -> bool:
        """Mark a task as failed and requeue when retries remain."""
        with self._lock:
            task = self._tasks[task_id]
            task.last_error = error
            self._running = max(0, self._running - 1)

            if task.attempts <= task.max_retries:
                task.mark(TaskStatus.PENDING)
                self._enqueue(task)
                return True

            task.mark(TaskStatus.FAILED)
            return False

    def queue_size(self) -> int:
        """Return the number of pending tasks."""
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status is TaskStatus.PENDING)

    def running_count(self) -> int:
        """Return the number of running tasks."""
        with self._lock:
            return self._running

    def completed_count(self) -> int:
        """Return the number of completed tasks."""
        with self._lock:
            return self._completed

    def list_tasks(self) -> list[QueuedTask]:
        """Return all known tasks."""
        with self._lock:
            return list(self._tasks.values())

    def _enqueue(self, task: QueuedTask) -> None:
        if self._mode is QueueMode.FIFO:
            self._fifo.append(task.task_id)
            return

        self._sequence += 1
        heapq.heappush(self._priority, (task.priority, self._sequence, task.task_id))

    def _pop_next_id(self) -> str | None:
        if self._mode is QueueMode.FIFO:
            if not self._fifo:
                return None
            return self._fifo.popleft()

        if not self._priority:
            return None
        return heapq.heappop(self._priority)[2]
