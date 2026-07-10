"""YouTube Agent production plugin for ClipPilot orchestration."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iris.agents.base_agent import BaseAgent
from iris.plugins.context import PluginContext
from iris.services.event_bus import Event
from iris.services.process_manager import ProcessSpec, ProcessStatus
from iris.services.task_queue import QueuedTask
from iris.utils.status import AgentStatus


@dataclass(frozen=True)
class YouTubeTaskResult:
    """Result returned by a completed YouTube Agent task."""

    task_id: str
    process_id: str
    status: str
    stdout: list[str]
    stderr: list[str]
    generated_video: str | None = None
    upload_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class YouTubeAgent(BaseAgent):
    """Orchestrates ClipPilot tasks without owning video generation logic."""

    EVENT_REQUESTED = "youtube.requested"
    EVENT_CANCEL = "youtube.cancel"

    def __init__(self, context: PluginContext) -> None:
        super().__init__(name="YouTube Agent", version="1.0.0", event_bus=context.event_bus)
        self._context = context
        self._logger = context.logger.bind(plugin=self.name)
        self._current_task_id: str | None = None
        self._current_process_id: str | None = None
        self._render_progress = 0
        self._upload_progress = 0
        self._recent_events: list[dict[str, Any]] = []
        self._last_generated_video: str | None = None
        self._last_upload_url: str | None = None
        self._last_result: YouTubeTaskResult | None = None
        self._initialized = False
        self.initialize()

    @property
    def last_result(self) -> YouTubeTaskResult | None:
        """Return the latest ClipPilot orchestration result."""
        return self._last_result

    def initialize(self) -> None:
        """Subscribe the agent to YouTube orchestration requests."""
        if self._initialized:
            return

        self.subscribe_event(self.EVENT_REQUESTED, self._on_requested)
        self.subscribe_event(self.EVENT_CANCEL, self._on_cancel_requested)
        self._status = AgentStatus.INITIALIZED
        self._initialized = True
        self._logger.info("YouTube Agent initialized")

    def run(self) -> None:
        """Mark the agent as running."""
        if not self._initialized:
            self.initialize()
        self._status = AgentStatus.RUNNING

    def stop(self) -> None:
        """Mark the agent as stopped."""
        self._status = AgentStatus.STOPPED

    def health(self) -> bool:
        """Return True when required dependencies are available."""
        return self._context.configuration.validate()

    def submit(self, payload: dict[str, Any] | None = None, priority: int = 50) -> str:
        """Queue a ClipPilot orchestration task and return the IRIS task id."""
        task = QueuedTask(
            name="youtube.clippilot.run",
            handler=self._execute_task,
            payload=payload or {},
            priority=priority,
            max_retries=0,
        )
        task_id = self._context.task_queue.add_task(task)
        self._logger.info("Queued YouTube task {}", task_id)
        return task_id

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Return dashboard-ready state for the YouTube Agent page."""
        process_state = "Not started"
        if self._current_process_id is not None:
            process_state = self._context.process_manager.get_status(self._current_process_id).value

        return {
            "status": self.status.value,
            "current_task": self._current_task_id or "--",
            "clip_pilot_process_state": process_state,
            "render_progress": self._render_progress,
            "upload_progress": self._upload_progress,
            "recent_events": list(self._recent_events[-20:]),
            "last_generated_video": self._last_generated_video or "--",
            "last_upload_url": self._last_upload_url or "--",
        }

    async def _on_requested(self, event: Event) -> None:
        task_id = self.submit(event.payload)
        await self._publish(
            "youtube.progress",
            {"task_id": task_id, "message": "Task accepted", "stage": "queued"},
        )

    async def _on_cancel_requested(self, event: Event) -> None:
        task_id = event.payload.get("task_id")
        if not isinstance(task_id, str):
            return

        self._context.task_queue.cancel_task(task_id)
        if self._current_task_id == task_id and self._current_process_id is not None:
            await self._context.process_manager.stop_process(self._current_process_id)

        await self._publish("youtube.cancelled", {"task_id": task_id})

    async def _execute_task(self, task: QueuedTask) -> YouTubeTaskResult:
        self._current_task_id = task.task_id
        self._render_progress = 0
        self._upload_progress = 0
        self._status = AgentStatus.RUNNING

        try:
            spec = self._build_process_spec(task.payload)
            await self._publish("youtube.started", {"task_id": task.task_id, "command": spec.command})
            process_id = await self._context.process_manager.launch(spec)
            self._current_process_id = process_id
        except FileNotFoundError as exc:
            self._status = AgentStatus.ERROR
            await self._publish_error(task.task_id, "missing_clip_pilot", str(exc))
            raise
        except ValueError as exc:
            self._status = AgentStatus.ERROR
            await self._publish_error(task.task_id, "invalid_configuration", str(exc))
            raise
        except Exception as exc:
            self._status = AgentStatus.ERROR
            await self._publish_error(task.task_id, "unexpected_crash", str(exc))
            raise

        try:
            result = await self._monitor_process(task.task_id, process_id)
        except RuntimeError:
            self._status = AgentStatus.ERROR
            raise
        except Exception as exc:
            self._status = AgentStatus.ERROR
            await self._publish_error(task.task_id, "unexpected_crash", str(exc))
            raise

        self._last_result = result
        self._status = AgentStatus.INITIALIZED
        self._current_task_id = None
        self._current_process_id = None
        return result

    def _build_process_spec(self, payload: dict[str, Any]) -> ProcessSpec:
        clip_pilot_path = self._required_path("youtube.clip_pilot_path")
        python_executable = self._context.configuration.get("youtube.python_executable")
        workspace = self._optional_path("youtube.workspace")
        timeout = self._timeout_seconds()
        arguments = self._arguments_from_payload(payload)

        if clip_pilot_path.is_dir():
            if not python_executable:
                raise ValueError("youtube.python_executable is required when ClipPilot path is a directory")
            command = [str(python_executable), "-m", "clippilot", *arguments]
            cwd = clip_pilot_path
        elif clip_pilot_path.suffix.lower() == ".py":
            executable = str(python_executable or "python")
            command = [executable, str(clip_pilot_path), *arguments]
            cwd = workspace
        else:
            command = [str(clip_pilot_path), *arguments]
            cwd = workspace

        return ProcessSpec(
            command=command,
            name="ClipPilot",
            cwd=cwd,
            timeout_seconds=timeout,
            restart_on_crash=False,
        )

    def _required_path(self, key: str) -> Path:
        value = self._context.configuration.get(key)
        if not value:
            raise ValueError(f"Missing required configuration: {key}")

        path = Path(str(value)).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Configured ClipPilot path does not exist: {path}")
        return path

    def _optional_path(self, key: str) -> Path | None:
        value = self._context.configuration.get(key)
        if not value:
            return None

        path = Path(str(value)).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _timeout_seconds(self) -> float | None:
        value = self._context.configuration.get("youtube.timeout_seconds")
        if value in (None, ""):
            return None
        return float(value)

    def _arguments_from_payload(self, payload: dict[str, Any]) -> list[str]:
        arguments = payload.get("arguments", [])
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise ValueError("YouTube task payload arguments must be a list of strings")

        if self._bool_config("youtube.auto_upload"):
            arguments = [*arguments, "--auto-upload"]
        return arguments

    def _bool_config(self, key: str) -> bool:
        value = self._context.configuration.get(key, False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    async def _monitor_process(self, task_id: str, process_id: str) -> YouTubeTaskResult:
        seen_stdout = 0
        seen_stderr = 0

        while True:
            status = self._context.process_manager.get_status(process_id)
            output = self._context.process_manager.get_output(process_id)

            for line in output["stdout"][seen_stdout:]:
                await self._publish_progress(task_id, process_id, "stdout", line, status)
            for line in output["stderr"][seen_stderr:]:
                await self._publish_progress(task_id, process_id, "stderr", line, status)

            seen_stdout = len(output["stdout"])
            seen_stderr = len(output["stderr"])

            if status in {ProcessStatus.STOPPED, ProcessStatus.CRASHED, ProcessStatus.TIMEOUT}:
                break

            await asyncio.sleep(0.25)

        output = self._context.process_manager.get_output(process_id)
        status = self._context.process_manager.get_status(process_id)
        result = YouTubeTaskResult(
            task_id=task_id,
            process_id=process_id,
            status=status.value,
            stdout=output["stdout"],
            stderr=output["stderr"],
            generated_video=self._last_generated_video,
            upload_url=self._last_upload_url,
        )

        if status is ProcessStatus.STOPPED:
            await self._publish(
                "youtube.completed",
                {
                    "task_id": task_id,
                    "process_id": process_id,
                    "generated_video": result.generated_video,
                    "upload_url": result.upload_url,
                },
            )
            return result

        error_code = "process_timeout" if status is ProcessStatus.TIMEOUT else "process_failed"
        await self._publish_error(task_id, error_code, f"ClipPilot ended with status {status.value}")
        raise RuntimeError(f"ClipPilot ended with status {status.value}")

    async def _publish_progress(
        self,
        task_id: str,
        process_id: str,
        stream: str,
        line: str,
        status: ProcessStatus,
    ) -> None:
        details = self._progress_from_line(line)
        render_progress = details.get("render_progress")
        upload_progress = details.get("upload_progress")
        if render_progress is not None:
            self._render_progress = int(render_progress)
        if upload_progress is not None:
            self._upload_progress = int(upload_progress)
        self._last_generated_video = details.get("generated_video", self._last_generated_video)
        self._last_upload_url = details.get("upload_url", self._last_upload_url)

        await self._publish(
            "youtube.progress",
            {
                "task_id": task_id,
                "process_id": process_id,
                "process_status": status.value,
                "stream": stream,
                "message": line,
                "render_progress": self._render_progress,
                "upload_progress": self._upload_progress,
                "generated_video": self._last_generated_video,
                "upload_url": self._last_upload_url,
            },
        )

    def _progress_from_line(self, line: str) -> dict[str, Any]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return self._progress_from_key_values(line)

        if not isinstance(data, dict):
            return {}

        return {
            "render_progress": data.get("render_progress", data.get("render")),
            "upload_progress": data.get("upload_progress", data.get("upload")),
            "generated_video": data.get("generated_video", data.get("video_path")),
            "upload_url": data.get("upload_url"),
        }

    def _progress_from_key_values(self, line: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for item in line.split():
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key in {"render_progress", "render"}:
                values["render_progress"] = value
            elif key in {"upload_progress", "upload"}:
                values["upload_progress"] = value
            elif key in {"generated_video", "video_path"}:
                values["generated_video"] = value
            elif key == "upload_url":
                values["upload_url"] = value
        return values

    async def _publish_error(self, task_id: str, code: str, message: str) -> None:
        await self._publish(
            "youtube.failed",
            {
                "task_id": task_id,
                "error": {
                    "code": code,
                    "message": message,
                    "process_id": self._current_process_id,
                },
            },
        )

    async def _publish(self, event_name: str, payload: dict[str, Any]) -> None:
        event = Event(event_name, payload, source=self.name)
        self._recent_events.append(
            {
                "name": event.name,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
        )
        await self.publish_event(event)
