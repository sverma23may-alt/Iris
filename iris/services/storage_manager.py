"""Storage folder management for IRIS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from iris.services.base import ManagedService
from iris.services.logger import get_logger


class StorageManager(ManagedService):
    """Create and resolve standard IRIS storage directories."""

    name = "Storage"
    version = "1.0.0"
    FOLDERS = ("videos", "logs", "cache", "downloads", "exports", "temp", "plugins")

    def __init__(self, root_path: Path | None = None) -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)
        self._root_path = (root_path or Path.cwd()).resolve()
        self._paths = {folder: self._root_path / folder for folder in self.FOLDERS}

    def start(self) -> None:
        """Create managed directories and mark the service as running."""
        self.ensure_directories()
        super().start()
        self._logger.info("Storage manager started at {}", self._root_path)

    def ensure_directories(self) -> None:
        """Create managed directories if they are missing."""
        for path in self._paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        """Return an absolute managed path by name."""
        return self._paths[name].resolve()

    def paths(self) -> dict[str, Path]:
        """Return all managed paths."""
        return {name: path.resolve() for name, path in self._paths.items()}

    def namespace_path(self, namespace: str) -> Path:
        """Return a managed namespace path under the storage root."""
        path = (self._root_path / namespace).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, namespace: str, filename: str, data: dict[str, Any]) -> Path:
        """Persist JSON data in a managed namespace."""
        path = self.namespace_path(namespace) / filename
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_json(
        self,
        namespace: str,
        filename: str,
        default: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Load JSON data from a managed namespace."""
        path = self.namespace_path(namespace) / filename
        if not path.exists():
            return dict(default or {})
        return json.loads(path.read_text(encoding="utf-8"))
