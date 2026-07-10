"""External process management for IRIS."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from iris.services.base import ManagedService
from iris.services.logger import get_logger


class ProcessStatus(str, Enum):
    """Managed process lifecycle status."""

    STARTING = "Starting"
    RUNNING = "Running"
    STOPPED = "Stopped"
    CRASHED = "Crashed"
    TIMEOUT = "Timeout"


@dataclass(frozen=True)
class ProcessSpec:
    """Launch specification for a managed external process."""

    command: list[str]
    name: str | None = None
    cwd: Path | None = None
    env: dict[str, str] | None = None
    timeout_seconds: float | None = None
    restart_on_crash: bool = False
    max_restarts: int = 3


@dataclass
class ManagedProcess:
    """Runtime state for an external process."""

    process_id: str
    spec: ProcessSpec
    process: asyncio.subprocess.Process
    status: ProcessStatus = ProcessStatus.STARTING
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    restart_count: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stopped_at: datetime | None = None


class ProcessManager(ManagedService):
    """Launch, monitor, restart, stop, and kill external processes."""

    name = "Process Manager"
    version = "1.0.0"

    def __init__(self) -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)
        self._processes: dict[str, ManagedProcess] = {}

    def start(self) -> None:
        """Mark the process manager as running."""
        super().start()
        self._logger.info("Process manager started")

    async def launch(self, spec: ProcessSpec) -> str:
        """Launch and monitor an external process."""
        process = await asyncio.create_subprocess_exec(
            *spec.command,
            cwd=spec.cwd,
            env=spec.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        process_id = str(uuid4())
        managed = ManagedProcess(
            process_id=process_id,
            spec=spec,
            process=process,
            status=ProcessStatus.RUNNING,
        )
        self._processes[process_id] = managed
        asyncio.create_task(self._capture_stream(process_id, process.stdout, "stdout"))
        asyncio.create_task(self._capture_stream(process_id, process.stderr, "stderr"))
        asyncio.create_task(self._monitor(process_id))
        self._logger.info("Launched process {}: {}", process_id, spec.command)
        return process_id

    def get_status(self, process_id: str) -> ProcessStatus:
        """Return the status of a managed process."""
        return self._processes[process_id].status

    def get_output(self, process_id: str) -> dict[str, list[str]]:
        """Return captured stdout and stderr for a process."""
        process = self._processes[process_id]
        return {"stdout": list(process.stdout), "stderr": list(process.stderr)}

    def list_processes(self) -> dict[str, ProcessStatus]:
        """Return statuses for all managed processes."""
        return {process_id: process.status for process_id, process in self._processes.items()}

    async def stop_process(self, process_id: str) -> None:
        """Gracefully stop a managed process."""
        process = self._processes[process_id]
        if process.process.returncode is None:
            process.process.terminate()
            await process.process.wait()
        process.status = ProcessStatus.STOPPED
        process.stopped_at = datetime.now(UTC)
        self._logger.info("Stopped process {}", process_id)

    async def kill_process(self, process_id: str) -> None:
        """Force kill a managed process."""
        process = self._processes[process_id]
        if process.process.returncode is None:
            process.process.kill()
            await process.process.wait()
        process.status = ProcessStatus.STOPPED
        process.stopped_at = datetime.now(UTC)
        self._logger.info("Killed process {}", process_id)

    async def restart_process(self, process_id: str) -> str:
        """Restart a managed process and return the new id."""
        process = self._processes[process_id]
        await self.stop_process(process_id)
        return await self.launch(process.spec)

    async def _capture_stream(
        self,
        process_id: str,
        stream: asyncio.StreamReader | None,
        stream_name: str,
    ) -> None:
        if stream is None:
            return

        process = self._processes[process_id]
        while line := await stream.readline():
            text = line.decode(errors="replace").rstrip()
            getattr(process, stream_name).append(text)
            self._logger.info("Process {} {}: {}", process_id, stream_name, text)

    async def _monitor(self, process_id: str) -> None:
        process = self._processes[process_id]
        try:
            await asyncio.wait_for(process.process.wait(), timeout=process.spec.timeout_seconds)
        except TimeoutError:
            if process.process.returncode is None:
                process.process.kill()
                await process.process.wait()
            process.status = ProcessStatus.TIMEOUT
            process.stopped_at = datetime.now(UTC)
            self._logger.warning("Process {} timed out", process_id)
            return

        if process.status is ProcessStatus.STOPPED:
            return

        if process.process.returncode == 0:
            process.status = ProcessStatus.STOPPED
            process.stopped_at = datetime.now(UTC)
            self._logger.info("Process {} exited normally", process_id)
            return

        process.status = ProcessStatus.CRASHED
        self._logger.warning("Process {} crashed with code {}", process_id, process.process.returncode)
        if (
            process.spec.restart_on_crash
            and process.restart_count < process.spec.max_restarts
        ):
            process.restart_count += 1
            await self.launch(process.spec)

    @property
    def healthy(self) -> bool:
        """Return True when the manager is running and no process has crashed."""
        return self.status.value == "Running" and all(
            process.status not in {ProcessStatus.CRASHED, ProcessStatus.TIMEOUT}
            for process in self._processes.values()
        )
