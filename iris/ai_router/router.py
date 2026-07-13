"""AI Router core service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from iris.ai_router.configuration import AIRouterConfiguration, RoutingMode
from iris.ai_router.exceptions import ProviderExecutionError, ProviderUnavailableError
from iris.ai_router.provider import AIProvider
from iris.ai_router.registry import ProviderRegistry
from iris.ai_router.response import AIResponse
from iris.services.base import ManagedService
from iris.services.logger import get_logger


ProviderCall = Callable[[AIProvider], AIResponse]


class AIRouter(ManagedService):
    """Provider-neutral routing service for future AI integrations."""

    name = "AI Router"
    version = "1.0.0"

    def __init__(
        self,
        configuration: AIRouterConfiguration | None = None,
        registry: ProviderRegistry | None = None,
    ) -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)
        self._configuration = configuration or AIRouterConfiguration()
        self._registry = registry or ProviderRegistry()
        self._latencies: dict[str, float] = {}
        self._last_success: dict[str, datetime] = {}
        self._current_provider: str | None = None

    @property
    def configuration(self) -> AIRouterConfiguration:
        """Return active router configuration."""
        return self._configuration

    @property
    def registry(self) -> ProviderRegistry:
        """Return provider registry."""
        return self._registry

    def start(self) -> None:
        """Discover providers and mark the router online."""
        self._registry.auto_discover()
        super().start()
        self._logger.info("AI Router started with providers: {}", self._registry.names())

    def register_provider(self, provider: AIProvider) -> None:
        """Register a provider instance."""
        self._registry.register(provider)

    def select_provider(self, provider_name: str | None = None) -> AIProvider:
        """Select a provider using explicit input and configured routing mode."""
        if provider_name:
            provider = self._registry.get(provider_name)
            if provider.is_available():
                return provider
            raise ProviderUnavailableError(f"Provider is unavailable: {provider_name}")

        mode = self._configuration.routing_mode
        if mode is RoutingMode.OFFLINE:
            return self._select_named_or_available(self._configuration.fallback_provider)
        if mode is RoutingMode.MANUAL:
            return self._select_named_or_available(self._configuration.preferred_provider)
        if mode is RoutingMode.COST_SAVING:
            return min(self._available_or_raise(), key=lambda item: item.estimated_cost(1000, 1000))
        if mode is RoutingMode.PERFORMANCE:
            return min(self._available_or_raise(), key=lambda item: self._latencies.get(item.name, float("inf")))
        if mode is RoutingMode.FUTURE_PROOF:
            return max(
                self._available_or_raise(),
                key=lambda item: (
                    item.supports_streaming(),
                    item.supports_images(),
                    item.supports_reasoning(),
                    item.max_context(),
                ),
            )
        return self._select_named_or_available(self._configuration.preferred_provider)

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        provider_name: str | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Execute a chat request through the selected provider."""
        return self._execute(provider_name, lambda provider: provider.chat(messages, model=model, **kwargs))

    def complete(
        self,
        prompt: str,
        model: str | None = None,
        provider_name: str | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Execute a completion request through the selected provider."""
        return self._execute(provider_name, lambda provider: provider.complete(prompt, model=model, **kwargs))

    def embed(
        self,
        text: str | list[str],
        model: str | None = None,
        provider_name: str | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Execute an embedding request through the selected provider."""
        return self._execute(provider_name, lambda provider: provider.embed(text, model=model, **kwargs))

    def vision(
        self,
        prompt: str,
        images: list[Any],
        model: str | None = None,
        provider_name: str | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Execute a vision request through the selected provider."""
        return self._execute(provider_name, lambda provider: provider.vision(prompt, images, model=model, **kwargs))

    def health_checks(self) -> dict[str, Any]:
        """Return provider availability, latency, status, and success details."""
        providers = []
        for provider in self._registry.list():
            health = provider.health()
            providers.append(
                {
                    **health,
                    "latency_ms": self._latencies.get(provider.name),
                    "last_successful_request": _iso(self._last_success.get(provider.name))
                    or health.get("last_successful_request"),
                }
            )
        return {
            "routing_mode": self._configuration.routing_mode.value,
            "current_provider": self._current_provider,
            "configuration": self._configuration.to_dict(),
            "providers": providers,
        }

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Return dashboard-ready AI Router state."""
        health = self.health_checks()
        return {
            "registered_providers": self._registry.names(),
            "provider_status": health["providers"],
            "routing_mode": health["routing_mode"],
            "current_provider": health["current_provider"] or self._preview_provider_name(),
            "configuration": health["configuration"],
        }

    def _execute(self, provider_name: str | None, operation: ProviderCall) -> AIResponse:
        provider = self.select_provider(provider_name)
        attempts = max(1, self._configuration.max_retries + 1)
        errors: list[str] = []
        for attempt in range(attempts):
            try:
                response = operation(provider)
            except Exception as exc:
                errors.append(str(exc))
                if attempt + 1 >= attempts:
                    return self._fallback_or_error(provider, operation, errors)
                continue
            self._record_success(provider.name, response.latency_ms)
            return response
        return self._fallback_or_error(provider, operation, errors)

    def _fallback_or_error(
        self,
        failed_provider: AIProvider,
        operation: ProviderCall,
        errors: list[str],
    ) -> AIResponse:
        fallback_name = self._configuration.fallback_provider
        if fallback_name and fallback_name != failed_provider.name:
            fallback = self._registry.get(fallback_name)
            if fallback.is_available():
                try:
                    response = operation(fallback)
                except Exception as exc:
                    errors.append(str(exc))
                else:
                    self._record_success(fallback.name, response.latency_ms)
                    return response
        message = "; ".join(errors) or "provider request failed"
        raise ProviderExecutionError(message)

    def _select_named_or_available(self, name: str | None) -> AIProvider:
        if name:
            provider = self._registry.get(name)
            if provider.is_available():
                return provider
        available = self._available_or_raise()
        return available[0]

    def _available_or_raise(self) -> list[AIProvider]:
        available = self._registry.available()
        if not available:
            raise ProviderUnavailableError("No AI providers are available")
        return available

    def _record_success(self, provider_name: str, latency_ms: float) -> None:
        self._current_provider = provider_name
        self._latencies[provider_name] = latency_ms
        self._last_success[provider_name] = datetime.now(UTC)

    def _preview_provider_name(self) -> str | None:
        try:
            return self.select_provider().name
        except Exception:
            return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
