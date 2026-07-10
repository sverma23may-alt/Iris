"""Tests for Sprint 2.5 system services."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from iris.core.iris_core import IrisCore
from iris.plugins.context import PluginContext
from iris.plugins.youtube_agent import YouTubeAgent
from iris.services.configuration_service import ConfigurationService
from iris.services.event_bus import EventBus
from iris.services.background_worker import BackgroundWorker
from iris.services.logger import get_logger
from iris.services.plugin_loader import PluginLoader
from iris.services.process_manager import ProcessManager, ProcessSpec, ProcessStatus
from iris.services.secrets_manager import SecretsManager
from iris.services.service_registry import ServiceRegistry
from iris.services.storage_manager import StorageManager
from iris.services.task_queue import TaskQueue


class ServiceRegistryTests(unittest.TestCase):
    """Service registry behavior."""

    def test_register_and_get_service(self) -> None:
        registry = ServiceRegistry()
        service = StorageManager()

        registry.register("storage", service)

        self.assertIs(registry.get("storage", StorageManager), service)


class ConfigurationServiceTests(unittest.TestCase):
    """Configuration service behavior."""

    def test_load_set_save_reload_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".env"
            config_file = root / "config.json"
            env_file.write_text("IRIS_APP_NAME=IRIS\nIRIS_ENVIRONMENT=test\n", encoding="utf-8")

            service = ConfigurationService(env_file=env_file, json_file=config_file)
            service.start()
            service.set("feature_flag", True)
            service.save()
            service.reload()

            self.assertTrue(service.validate())
            self.assertTrue(service.get("feature_flag"))


class StorageManagerTests(unittest.TestCase):
    """Storage manager behavior."""

    def test_creates_managed_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = StorageManager(root_path=Path(directory))
            service.start()

            for path in service.paths().values():
                self.assertTrue(path.exists())
                self.assertTrue(path.is_absolute())


class SecretsManagerTests(unittest.TestCase):
    """Secrets manager behavior."""

    def test_reads_secret_keys_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("OPENAI_API_KEY=test-key\nPLAIN_VALUE=nope\n", encoding="utf-8")

            service = SecretsManager(env_file=env_file)
            service.start()

            self.assertEqual(service.get("OPENAI_API_KEY"), "test-key")
            self.assertNotIn("PLAIN_VALUE", service.keys())


class ProcessManagerTests(unittest.IsolatedAsyncioTestCase):
    """Process manager behavior."""

    async def test_launch_captures_stdout(self) -> None:
        manager = ProcessManager()
        manager.start()

        process_id = await manager.launch(
            ProcessSpec(
                command=[
                    sys.executable,
                    "-c",
                    "print('hello from iris')",
                ]
            )
        )
        await asyncio.sleep(0.5)

        self.assertEqual(manager.get_status(process_id), ProcessStatus.STOPPED)
        self.assertIn("hello from iris", manager.get_output(process_id)["stdout"])


class PluginLoaderTests(unittest.TestCase):
    """Plugin loader compatibility behavior."""

    def test_legacy_plugin_without_context_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_path = Path(directory)
            (plugins_path / "legacy_plugin.py").write_text(
                """
from iris.agents.base_agent import BaseAgent

class LegacyAgent(BaseAgent):
    def __init__(self):
        super().__init__("Legacy Agent", "1.0.0")
    def initialize(self): pass
    def run(self): pass
    def stop(self): pass
    def health(self): return True
""",
                encoding="utf-8",
            )

            agents = PluginLoader(plugins_path=plugins_path).discover()

            self.assertEqual(len(agents), 1)
            self.assertEqual(agents[0].name, "Legacy Agent")

    def test_context_aware_plugin_receives_plugin_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_path = Path(directory)
            (plugins_path / "context_plugin.py").write_text(
                """
from iris.agents.base_agent import BaseAgent
from iris.plugins.context import PluginContext

class ContextAgent(BaseAgent):
    def __init__(self, context: PluginContext):
        super().__init__("Context Agent", "1.0.0", event_bus=context.event_bus)
        self.context = context
    def initialize(self): pass
    def run(self): pass
    def stop(self): pass
    def health(self): return True
""",
                encoding="utf-8",
            )
            context = self._context()

            agents = PluginLoader(plugins_path=plugins_path, context=context).discover()

            self.assertEqual(len(agents), 1)
            self.assertIs(agents[0].context, context)

    def _context(self) -> PluginContext:
        registry = ServiceRegistry()
        event_bus = EventBus()
        task_queue = TaskQueue()
        process_manager = ProcessManager()
        configuration = ConfigurationService()
        registry.register("event_bus", event_bus)
        registry.register("task_queue", task_queue)
        registry.register("process_manager", process_manager)
        registry.register("configuration", configuration)
        return PluginContext(
            event_bus=event_bus,
            task_queue=task_queue,
            process_manager=process_manager,
            configuration=configuration,
            service_registry=registry,
            logger=get_logger("test.plugins"),
        )


class YouTubeAgentTests(unittest.IsolatedAsyncioTestCase):
    """YouTube Agent orchestration behavior."""

    async def test_runs_mock_clippilot_process_through_task_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mock_clippilot = root / "mock_clippilot.py"
            mock_clippilot.write_text(
                "import json\n"
                "print(json.dumps({'render_progress': 25}), flush=True)\n"
                "print(json.dumps({'render_progress': 100, 'upload_progress': 100, "
                "'video_path': 'video.mp4', 'upload_url': 'https://youtu.be/test'}), flush=True)\n",
                encoding="utf-8",
            )

            event_bus = EventBus()
            task_queue = TaskQueue()
            process_manager = ProcessManager()
            process_manager.start()
            configuration = ConfigurationService()
            configuration.set("youtube.clip_pilot_path", str(mock_clippilot))
            configuration.set("youtube.python_executable", sys.executable)
            configuration.set("youtube.workspace", str(root))
            configuration.set("youtube.timeout_seconds", 5)
            configuration.set("youtube.auto_upload", False)
            registry = ServiceRegistry()
            context = PluginContext(
                event_bus=event_bus,
                task_queue=task_queue,
                process_manager=process_manager,
                configuration=configuration,
                service_registry=registry,
                logger=get_logger("test.youtube"),
            )
            events = []
            event_bus.subscribe("*", lambda event: events.append(event))
            agent = YouTubeAgent(context)
            worker = BackgroundWorker(task_queue, event_bus, poll_interval_seconds=0.05)

            agent.submit({"arguments": []})
            await worker.start()
            for _ in range(100):
                if task_queue.completed_count() == 1:
                    break
                await asyncio.sleep(0.05)
            await worker.stop()

            self.assertEqual(task_queue.completed_count(), 1)
            self.assertIsNotNone(agent.last_result)
            self.assertEqual(agent.last_result.generated_video, "video.mp4")
            self.assertEqual(agent.last_result.upload_url, "https://youtu.be/test")
            self.assertIn("youtube.completed", {event.name for event in events})

    async def test_missing_clippilot_configuration_fails_with_structured_event(self) -> None:
        event_bus = EventBus()
        events = []
        event_bus.subscribe("*", lambda event: events.append(event))
        context = PluginContext(
            event_bus=event_bus,
            task_queue=TaskQueue(),
            process_manager=ProcessManager(),
            configuration=ConfigurationService(),
            service_registry=ServiceRegistry(),
            logger=get_logger("test.youtube"),
        )
        agent = YouTubeAgent(context)
        task_id = agent.submit()
        task = context.task_queue.get_next_task()

        self.assertIsNotNone(task)
        with self.assertRaises(ValueError):
            await task.handler(task)

        failed_events = [event for event in events if event.name == "youtube.failed"]
        self.assertEqual(len(failed_events), 1)
        self.assertEqual(failed_events[0].payload["error"]["code"], "invalid_configuration")


class IrisCoreServiceTests(unittest.TestCase):
    """Core service registry integration."""

    def test_core_exposes_system_services_in_status(self) -> None:
        core = IrisCore()
        core.start()
        status = core.get_status()
        core.stop()

        names = {service["name"] for service in status.services}
        self.assertIn("Configuration", names)
        self.assertIn("Service Registry", names)


if __name__ == "__main__":
    unittest.main()
