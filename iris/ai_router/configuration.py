"""AI Router configuration model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RoutingMode(str, Enum):
    """Supported AI Router provider-selection strategies."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    OFFLINE = "offline"
    COST_SAVING = "cost_saving"
    PERFORMANCE = "performance"
    FUTURE_PROOF = "future_proof"


@dataclass(slots=True)
class AIRouterConfiguration:
    """Runtime configuration for AI Router provider selection."""

    preferred_provider: str | None = None
    fallback_provider: str | None = "mock"
    routing_mode: RoutingMode = RoutingMode.AUTOMATIC
    timeout: float = 30.0
    max_retries: int = 1
    streaming: bool = False

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "AIRouterConfiguration":
        """Create router configuration from a primitive mapping."""
        mode = values.get("ai_router.routing_mode", values.get("routing_mode", RoutingMode.AUTOMATIC.value))
        return cls(
            preferred_provider=_optional_string(
                values.get("ai_router.preferred_provider", values.get("preferred_provider"))
            ),
            fallback_provider=_optional_string(
                values.get("ai_router.fallback_provider", values.get("fallback_provider", "mock"))
            ),
            routing_mode=RoutingMode(str(mode)),
            timeout=float(values.get("ai_router.timeout", values.get("timeout", 30.0)) or 30.0),
            max_retries=int(values.get("ai_router.max_retries", values.get("max_retries", 1)) or 0),
            streaming=_bool_value(values.get("ai_router.streaming", values.get("streaming", False))),
        )

    @classmethod
    def from_configuration_service(cls, configuration: Any) -> "AIRouterConfiguration":
        """Create router configuration from the existing IRIS configuration service."""
        values = {
            "ai_router.preferred_provider": configuration.get("ai_router.preferred_provider"),
            "ai_router.fallback_provider": configuration.get("ai_router.fallback_provider", "mock"),
            "ai_router.routing_mode": configuration.get("ai_router.routing_mode", "automatic"),
            "ai_router.timeout": configuration.get("ai_router.timeout", 30.0),
            "ai_router.max_retries": configuration.get("ai_router.max_retries", 1),
            "ai_router.streaming": configuration.get("ai_router.streaming", False),
        }
        return cls.from_mapping(values)

    def to_dict(self) -> dict[str, Any]:
        """Return a primitive dashboard representation."""
        return {
            "preferred_provider": self.preferred_provider,
            "fallback_provider": self.fallback_provider,
            "routing_mode": self.routing_mode.value,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "streaming": self.streaming,
        }


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
