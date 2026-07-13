"""Provider registry for AI Router."""

from __future__ import annotations

from collections.abc import Iterable

from iris.ai_router.exceptions import ProviderNotFoundError
from iris.ai_router.provider import AIProvider
from iris.ai_router.providers.mock import MockProvider


_REGISTERED_PROVIDER_TYPES: dict[str, type[AIProvider]] = {}


def register_provider_type(provider_type: type[AIProvider]) -> type[AIProvider]:
    """Register a provider class for auto-discovery."""
    _REGISTERED_PROVIDER_TYPES[provider_type.name] = provider_type
    return provider_type


class ProviderRegistry:
    """Registry for concrete provider instances."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        """Register a concrete provider instance."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> AIProvider:
        """Return a provider by name."""
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderNotFoundError(f"Provider is not registered: {name}") from exc

    def list(self) -> list[AIProvider]:
        """Return all registered providers."""
        return list(self._providers.values())

    def names(self) -> list[str]:
        """Return provider names."""
        return sorted(self._providers)

    def available(self) -> list[AIProvider]:
        """Return currently available providers."""
        return [provider for provider in self.list() if provider.is_available()]

    def auto_discover(self) -> None:
        """Register built-in providers and provider classes that self-registered."""
        register_provider_type(MockProvider)
        for provider_type in _REGISTERED_PROVIDER_TYPES.values():
            if provider_type.name not in self._providers:
                self.register(provider_type())

    def extend(self, providers: Iterable[AIProvider]) -> None:
        """Register multiple providers."""
        for provider in providers:
            self.register(provider)
