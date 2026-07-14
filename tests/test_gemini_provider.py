"""Tests for Sprint 8.1 Gemini provider. No live API calls are made."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from iris.ai_router.configuration import AIRouterConfiguration, RoutingMode
from iris.ai_router.providers.gemini import GeminiProvider
from iris.ai_router.providers.mock import MockProvider
from iris.ai_router.registry import ProviderRegistry
from iris.ai_router.router import AIRouter


def _fake_generate_response(text: str, prompt_tokens: int = 3, completion_tokens: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=completion_tokens,
            total_token_count=prompt_tokens + completion_tokens,
        ),
    )


class GeminiProviderAvailabilityTests(unittest.TestCase):
    """Availability must depend only on API key + SDK presence, never raise."""

    def test_unavailable_without_api_key(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            provider = GeminiProvider()

        self.assertFalse(provider.is_available())

    def test_unavailable_when_sdk_missing(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai", None):
                provider = GeminiProvider()

        self.assertFalse(provider.is_available())

    def test_available_with_key_and_sdk(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai") as fake_genai:
                fake_genai.Client.return_value = MagicMock()
                provider = GeminiProvider()

        self.assertTrue(provider.is_available())

    def test_client_construction_failure_leaves_provider_unavailable(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai") as fake_genai:
                fake_genai.Client.side_effect = RuntimeError("bad key")
                provider = GeminiProvider()

        self.assertFalse(provider.is_available())

    def test_missing_key_operations_raise_without_leaking_ui(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            provider = GeminiProvider()

        with self.assertRaises(RuntimeError):
            provider.complete("hello")


class GeminiProviderRequestTests(unittest.TestCase):
    """Chat, completion, embedding, and vision behavior against a mocked client."""

    def _provider_with_client(self, client: MagicMock) -> GeminiProvider:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai") as fake_genai:
                fake_genai.Client.return_value = client
                return GeminiProvider()

    def test_chat_returns_ai_response(self) -> None:
        client = MagicMock()
        client.models.generate_content.return_value = _fake_generate_response("Hello there")
        provider = self._provider_with_client(client)

        response = provider.chat([{"role": "user", "content": "hi"}])

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(response.model, GeminiProvider.default_model)
        self.assertEqual(response.response, "Hello there")
        self.assertEqual(response.tokens_prompt, 3)
        self.assertEqual(response.tokens_completion, 5)
        self.assertEqual(response.total_tokens, 8)

    def test_complete_uses_model_override(self) -> None:
        client = MagicMock()
        client.models.generate_content.return_value = _fake_generate_response("done")
        provider = self._provider_with_client(client)

        response = provider.complete("write a haiku", model="gemini-2.5-pro")

        client.models.generate_content.assert_called_once_with(model="gemini-2.5-pro", contents="write a haiku")
        self.assertEqual(response.model, "gemini-2.5-pro")

    def test_embed_returns_ai_response(self) -> None:
        client = MagicMock()
        client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3])]
        )
        provider = self._provider_with_client(client)

        response = provider.embed("hello world")

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(response.response, [[0.1, 0.2, 0.3]])

    def test_vision_delegates_to_generate_content(self) -> None:
        client = MagicMock()
        client.models.generate_content.return_value = _fake_generate_response("a red apple")
        provider = self._provider_with_client(client)

        response = provider.vision("describe this", images=["fake-image-bytes"])

        self.assertTrue(response.success)
        self.assertEqual(response.response, "a red apple")

    def test_generate_failure_raises_and_redacts_key(self) -> None:
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("401 unauthorized key=fake-key")
        provider = self._provider_with_client(client)

        with self.assertRaises(RuntimeError) as ctx:
            provider.complete("hello")

        self.assertNotIn("fake-key", str(ctx.exception))
        self.assertIn("redacted", str(ctx.exception))

    def test_health_report_never_exposes_api_key(self) -> None:
        client = MagicMock()
        provider = self._provider_with_client(client)

        health = provider.health()

        self.assertNotIn("fake-key", str(health))
        self.assertNotIn("api_key", health)


class GeminiProviderCapabilityTests(unittest.TestCase):
    """Capability reporting must be accurate, not inherited placeholder defaults."""

    def test_capabilities_are_accurate(self) -> None:
        provider = GeminiProvider()

        self.assertTrue(provider.supports_streaming())
        self.assertTrue(provider.supports_images())
        self.assertTrue(provider.supports_reasoning())
        self.assertEqual(provider.max_context(), 1_048_576)
        self.assertEqual(provider.max_context("gemini-2.5-pro"), 1_048_576)


class GeminiRegistryIntegrationTests(unittest.TestCase):
    """Gemini must auto-register through the existing ProviderRegistry."""

    def test_auto_discover_registers_gemini(self) -> None:
        registry = ProviderRegistry()
        registry.auto_discover()

        self.assertIn("gemini", registry.names())
        self.assertIsInstance(registry.get("gemini"), GeminiProvider)


class GeminiRouterFallbackTests(unittest.TestCase):
    """AIRouter's existing fallback logic must work unchanged with Gemini."""

    def test_router_skips_unavailable_gemini_without_error(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            registry = ProviderRegistry()
            registry.register(GeminiProvider())
            registry.register(MockProvider())
            router = AIRouter(
                AIRouterConfiguration(routing_mode=RoutingMode.AUTOMATIC, fallback_provider="mock"),
                registry=registry,
            )
            router.start()

            response = router.chat([{"role": "user", "content": "hi"}])

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "mock")

    def test_router_falls_back_to_mock_when_gemini_request_fails(self) -> None:
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("temporary outage")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai") as fake_genai:
                fake_genai.Client.return_value = client
                gemini_provider = GeminiProvider()

            registry = ProviderRegistry()
            registry.register(gemini_provider)
            registry.register(MockProvider())
            router = AIRouter(
                AIRouterConfiguration(
                    preferred_provider="gemini",
                    fallback_provider="mock",
                    routing_mode=RoutingMode.AUTOMATIC,
                    max_retries=0,
                ),
                registry=registry,
            )
            router.start()

            response = router.complete("hello")

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "mock")

    def test_router_reports_gemini_status_in_dashboard_snapshot(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            registry = ProviderRegistry()
            registry.register(GeminiProvider())
            registry.register(MockProvider())
            router = AIRouter(AIRouterConfiguration(fallback_provider="mock"), registry=registry)
            router.start()

            snapshot = router.dashboard_snapshot()

        self.assertIn("gemini", snapshot["registered_providers"])
        gemini_status = next(item for item in snapshot["provider_status"] if item["name"] == "gemini")
        self.assertFalse(gemini_status["available"])
        self.assertEqual(gemini_status["status"], "Unavailable")


if __name__ == "__main__":
    unittest.main()
