"""AI Router exception types."""

from __future__ import annotations


class AIRouterError(Exception):
    """Base exception for AI Router failures."""


class ProviderNotFoundError(AIRouterError):
    """Raised when a requested provider is not registered."""


class ProviderUnavailableError(AIRouterError):
    """Raised when no usable provider is available."""


class ProviderExecutionError(AIRouterError):
    """Raised when a provider request fails."""
