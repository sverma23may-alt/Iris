"""Tests for Sprint 7 AI Router architecture."""

from __future__ import annotations

import unittest
from typing import Any

from iris.ai_router.configuration import AIRouterConfiguration, RoutingMode
from iris.ai_router.exceptions import ProviderExecutionError
from iris.ai_router.providers.mock import MockProvider
from iris.ai_router.registry import ProviderRegistry
from iris.ai_router.response import AIResponse
from iris.ai_router.router import AIRouter
from iris.services.configuration_service import ConfigurationService


class AIRouterResponseTests(unittest.TestCase):
    """AIResponse behavior."""

    def test_response_object_serializes(self) -> None:
        response = AIResponse(
            provider="mock",
            model="mock-router-001",
            response="hello",
            latency_ms=1.5,
            estimated_cost=0.0,
            tokens_prompt=1,
            tokens_completion=1,
            total_tokens=2,
            success=True,
            metadata={"mock": True},
        )

        self.assertEqual(response.to_dict()["provider"], "mock")
        self.assertTrue(response.to_dict()["success"])


class ProviderRegistryTests(unittest.TestCase):
    """Provider registration behavior."""

    def test_registers_provider_and_auto_discovers_mock(self) -> None:
        registry = ProviderRegistry()
        registry.auto_discover()

        self.assertIn("mock", registry.names())
        self.assertIsInstance(registry.get("mock"), MockProvider)

    def test_manual_provider_registration(self) -> None:
        registry = ProviderRegistry()
        provider = MockProvider()

        registry.register(provider)

        self.assertIs(registry.get("mock"), provider)


class AIRouterConfigurationTests(unittest.TestCase):
    """Router configuration loading behavior."""

    def test_loads_from_configuration_service(self) -> None:
        configuration = ConfigurationService()
        configuration.set("ai_router.preferred_provider", "mock")
        configuration.set("ai_router.fallback_provider", "mock")
        configuration.set("ai_router.routing_mode", "manual")
        configuration.set("ai_router.timeout", 12)
        configuration.set("ai_router.max_retries", 2)
        configuration.set("ai_router.streaming", "true")

        router_config = AIRouterConfiguration.from_configuration_service(configuration)

        self.assertEqual(router_config.preferred_provider, "mock")
        self.assertEqual(router_config.routing_mode, RoutingMode.MANUAL)
        self.assertEqual(router_config.timeout, 12.0)
        self.assertEqual(router_config.max_retries, 2)
        self.assertTrue(router_config.streaming)


class AIRouterTests(unittest.TestCase):
    """Router selection, execution, fallback, and health behavior."""

    def test_selects_and_executes_mock_provider(self) -> None:
        router = AIRouter()
        router.start()

        response = router.chat([{"role": "user", "content": "hello"}])

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "mock")
        self.assertIn("Mock chat response", response.response)

    def test_manual_selection_uses_preferred_provider(self) -> None:
        router = AIRouter(
            AIRouterConfiguration(
                preferred_provider="mock",
                fallback_provider="mock",
                routing_mode=RoutingMode.MANUAL,
            )
        )
        router.start()

        self.assertEqual(router.select_provider().name, "mock")

    def test_fallback_uses_mock_after_provider_failure(self) -> None:
        registry = ProviderRegistry()
        registry.register(FailingProvider())
        registry.register(MockProvider())
        router = AIRouter(
            AIRouterConfiguration(
                preferred_provider="failing",
                fallback_provider="mock",
                routing_mode=RoutingMode.AUTOMATIC,
                max_retries=0,
            ),
            registry=registry,
        )
        router.start()

        response = router.complete("fall back please")

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "mock")

    def test_raises_when_provider_and_fallback_fail(self) -> None:
        registry = ProviderRegistry()
        registry.register(FailingProvider())
        router = AIRouter(
            AIRouterConfiguration(
                preferred_provider="failing",
                fallback_provider=None,
                routing_mode=RoutingMode.AUTOMATIC,
                max_retries=0,
            ),
            registry=registry,
        )
        router.start()

        with self.assertRaises(ProviderExecutionError):
            router.complete("fail")

    def test_health_checks_include_latency_and_current_provider(self) -> None:
        router = AIRouter()
        router.start()
        router.complete("health")

        health = router.health_checks()

        self.assertEqual(health["current_provider"], "mock")
        self.assertEqual(health["routing_mode"], "automatic")
        self.assertEqual(health["providers"][0]["name"], "mock")
        self.assertIsNotNone(health["providers"][0]["latency_ms"])


class FailingProvider(MockProvider):
    """Provider test double that fails requests."""

    name = "failing"

    def complete(self, prompt: str, model: str | None = None, **kwargs: Any) -> AIResponse:
        raise RuntimeError("provider unavailable")

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> AIResponse:
        raise RuntimeError("provider unavailable")


if __name__ == "__main__":
    unittest.main()
