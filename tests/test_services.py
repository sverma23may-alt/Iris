"""Tests for Sprint 2.5 system services."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from iris.core.iris_core import IrisCore
from iris.services.configuration_service import ConfigurationService
from iris.services.process_manager import ProcessManager, ProcessSpec, ProcessStatus
from iris.services.secrets_manager import SecretsManager
from iris.services.service_registry import ServiceRegistry
from iris.services.storage_manager import StorageManager


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
