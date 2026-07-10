"""Common service contracts for IRIS infrastructure services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ManagedServiceStatus(str, Enum):
    """Lifecycle status for managed system services."""

    RUNNING = "Running"
    STOPPED = "Stopped"


@dataclass(frozen=True)
class ServiceHealth:
    """Read-only health summary for a managed service."""

    name: str
    status: ManagedServiceStatus
    healthy: bool
    version: str


class ManagedService:
    """Base class for registry-managed infrastructure services."""

    name: str = "Service"
    version: str = "1.0.0"

    def __init__(self) -> None:
        self._status = ManagedServiceStatus.STOPPED

    @property
    def status(self) -> ManagedServiceStatus:
        """Return the service lifecycle status."""
        return self._status

    @property
    def healthy(self) -> bool:
        """Return True when the service is healthy."""
        return self._status is ManagedServiceStatus.RUNNING

    def start(self) -> None:
        """Mark the service as running."""
        self._status = ManagedServiceStatus.RUNNING

    def stop(self) -> None:
        """Mark the service as stopped."""
        self._status = ManagedServiceStatus.STOPPED

    def health(self) -> ServiceHealth:
        """Return the service health snapshot."""
        return ServiceHealth(
            name=self.name,
            status=self.status,
            healthy=self.healthy,
            version=self.version,
        )
