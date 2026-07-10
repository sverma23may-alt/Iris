"""Secrets management for IRIS."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from iris.services.base import ManagedService
from iris.services.logger import get_logger


class SecretsManager(ManagedService):
    """Read secrets from environment variables with a future encrypted-storage boundary."""

    name = "Secrets"
    version = "1.0.0"
    SECRET_HINTS = ("API_KEY", "TOKEN", "REFRESH_TOKEN", "OAUTH", "LLM_KEY")

    def __init__(self, env_file: Path | str = ".env") -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)
        self._env_file = Path(env_file)
        self._secrets: dict[str, str] = {}

    def start(self) -> None:
        """Load secrets and mark the service as running."""
        self.reload()
        super().start()
        self._logger.info("Secrets manager started")

    def reload(self) -> None:
        """Reload secrets from .env and process environment."""
        load_dotenv(dotenv_path=self._env_file)
        values = {key: value for key, value in dotenv_values(self._env_file).items() if value}
        values.update({key: value for key, value in os.environ.items() if self._is_secret_key(key)})
        self._secrets = {key: value for key, value in values.items() if self._is_secret_key(key)}
        self._logger.info("Secrets reloaded; {} secret keys available", len(self._secrets))

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return a secret value by key."""
        return self._secrets.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Set a secret in memory."""
        self._secrets[key] = value
        self._logger.info("Secret value updated: {}", key)

    def keys(self) -> list[str]:
        """Return available secret keys without exposing values."""
        return sorted(self._secrets)

    def save(self) -> None:
        """Placeholder for future encrypted secret persistence."""
        raise NotImplementedError("Encrypted secret persistence is planned for a future sprint")

    def _is_secret_key(self, key: str) -> bool:
        normalized = key.upper()
        return any(hint in normalized for hint in self.SECRET_HINTS)
