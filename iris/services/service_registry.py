"""Service registry for IRIS infrastructure services."""

from __future__ import annotations

from typing import TypeVar, cast

from iris.services.base import ManagedService, ServiceHealth
from iris.services.logger import get_logger


T = TypeVar("T")


class ServiceRegistry(ManagedService):
    """Central registry for dependency-injected services."""

    name = "Service Registry"
    version = "1.0.0"

    def __init__(self) -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)
        self._services: dict[str, object] = {}
        self.register(self.name, self)

    def register(self, name: str, service: object) -> None:
        """Register a service instance by name."""
        self._services[name] = service
        self._logger.info("Registered service: {}", name)

    def unregister(self, name: str) -> None:
        """Remove a service from the registry."""
        if name == self.name:
            raise ValueError("The service registry cannot unregister itself")

        del self._services[name]
        self._logger.info("Unregistered service: {}", name)

    def get(self, name: str, service_type: type[T] | None = None) -> T:
        """Return a registered service by name."""
        service = self._services[name]
        if service_type is not None and not isinstance(service, service_type):
            raise TypeError(f"Service {name} is not {service_type.__name__}")

        return cast(T, service)

    def list_services(self) -> dict[str, object]:
        """Return registered services keyed by name."""
        return dict(self._services)

    def health_report(self, names: list[str] | None = None) -> list[ServiceHealth]:
        """Return health snapshots for managed services."""
        selected = names or list(self._services)
        report: list[ServiceHealth] = []
        for name in selected:
            service = self._services.get(name)
            if isinstance(service, ManagedService):
                report.append(service.health())
        return report

    @property
    def healthy(self) -> bool:
        """Return True when the registry contains services."""
        return bool(self._services)
