"""Centralized configuration manager for IRIS."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv

from iris.services.base import ManagedService
from iris.services.logger import get_logger


class ConfigurationService(ManagedService):
    """Manage IRIS configuration from .env and config.json."""

    name = "Configuration"
    version = "1.0.0"

    def __init__(
        self,
        env_file: Path | str = ".env",
        json_file: Path | str = "config.json",
    ) -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)
        self._env_file = Path(env_file)
        self._json_file = Path(json_file)
        self._settings: dict[str, Any] = {}

    def start(self) -> None:
        """Load configuration and mark the service as running."""
        self.reload()
        super().start()
        self._logger.info("Configuration service started")

    def get(self, key: str, default: Any = None) -> Any:
        """Return a configuration value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value in memory."""
        self._settings[key] = value
        self._logger.info("Configuration value updated: {}", key)

    def save(self) -> None:
        """Persist current configuration to config.json."""
        self._json_file.parent.mkdir(parents=True, exist_ok=True)
        self._json_file.write_text(
            json.dumps(self._settings, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._logger.info("Configuration saved to {}", self._json_file)

    def reload(self) -> None:
        """Reload configuration from supported sources."""
        load_dotenv(dotenv_path=self._env_file)
        settings: dict[str, Any] = {}

        if self._json_file.exists():
            settings.update(json.loads(self._json_file.read_text(encoding="utf-8")))

        settings.update({key: value for key, value in dotenv_values(self._env_file).items()})
        settings.update(
            {
                "IRIS_APP_NAME": os.getenv("IRIS_APP_NAME", settings.get("IRIS_APP_NAME", "IRIS")),
                "IRIS_ENVIRONMENT": os.getenv(
                    "IRIS_ENVIRONMENT",
                    settings.get("IRIS_ENVIRONMENT", "development"),
                ),
                "IRIS_LOG_LEVEL": os.getenv(
                    "IRIS_LOG_LEVEL",
                    settings.get("IRIS_LOG_LEVEL", "INFO"),
                ),
                "IRIS_LOG_FILE": os.getenv(
                    "IRIS_LOG_FILE",
                    settings.get("IRIS_LOG_FILE", "logs/iris.log"),
                ),
            }
        )
        self._settings = settings
        self._logger.info("Configuration reloaded")

    def validate(self) -> bool:
        """Validate required configuration values."""
        required = ("IRIS_APP_NAME", "IRIS_ENVIRONMENT", "IRIS_LOG_LEVEL", "IRIS_LOG_FILE")
        valid = all(bool(self._settings.get(key)) for key in required)
        self._logger.info("Configuration validation result: {}", valid)
        return valid

    def load_yaml(self) -> None:
        """Placeholder for future YAML configuration support."""
        raise NotImplementedError("YAML configuration support is planned for a future sprint")
