"""Tests for Sprint 8.2 Chat integration.

Covers the MainWindow -> DashboardViewModel -> AIRouter -> Provider path at
the ViewModel layer (no Qt/GUI dependency, matching the existing test suite's
conventions). All Gemini calls are mocked; no live network access is used.
"""

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
from iris.core.iris_core import IrisCore
from iris.services.logger import LogBuffer
from iris.services.metrics import MetricsService
from iris.vision.view_model import ChatMessage, ChatResult, DashboardViewModel


def _core_with_router(registry: ProviderRegistry, configuration: AIRouterConfiguration | None = None) -> IrisCore:
    """Build a real IrisCore, replacing only its AIRouter with one backed by a controlled registry."""
    core = IrisCore()
    router = AIRouter(configuration or AIRouterConfiguration(fallback_provider="mock"), registry=registry)
    core.service_registry.register("ai_router", router)
    core.start()
    return core


def _view_model(core: IrisCore) -> DashboardViewModel:
    return DashboardViewModel(core=core, metrics_service=MetricsService(), log_buffer=LogBuffer(200))


def _fake_generate_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=4, candidates_token_count=6, total_token_count=10),
    )


class ChatReachesRouterTests(unittest.TestCase):
    """The ViewModel must call through AIRouter.chat(), never a provider directly."""

    def test_send_message_invokes_ai_router_chat(self) -> None:
        registry = ProviderRegistry()
        registry.register(MockProvider())
        core = _core_with_router(registry)
        view_model = _view_model(core)

        router = core.service_registry.get("ai_router", AIRouter)
        with patch.object(router, "chat", wraps=router.chat) as spy:
            view_model.append_user_message("hi there")
            view_model.request_assistant_reply()

        spy.assert_called()
        core.stop()

    def test_chat_payload_includes_conversation_history(self) -> None:
        registry = ProviderRegistry()
        registry.register(MockProvider())
        core = _core_with_router(registry)
        view_model = _view_model(core)
        router = core.service_registry.get("ai_router", AIRouter)

        view_model.append_user_message("first message")
        view_model.request_assistant_reply()
        view_model.append_user_message("second message")

        with patch.object(router, "chat", wraps=router.chat) as spy:
            view_model.request_assistant_reply()

        sent_payload = spy.call_args.args[0]
        texts = [entry["content"] for entry in sent_payload]
        self.assertIn("first message", texts)
        self.assertIn("second message", texts)
        core.stop()


class GeminiSuccessTests(unittest.TestCase):
    """When Gemini is available and succeeds, its response reaches chat history untouched."""

    def test_gemini_success_populates_chat_history(self) -> None:
        client = MagicMock()
        client.models.generate_content.return_value = _fake_generate_response("Hello from Gemini")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai") as fake_genai:
                fake_genai.Client.return_value = client
                registry = ProviderRegistry()
                registry.register(GeminiProvider())
                registry.register(MockProvider())
                core = _core_with_router(registry)
                view_model = _view_model(core)

                view_model.append_user_message("Are you there?")
                result = view_model.request_assistant_reply()

        self.assertIsInstance(result, ChatResult)
        self.assertFalse(result.used_fallback)
        self.assertIsNone(result.notice)
        self.assertEqual(result.message.provider, "gemini")
        self.assertEqual(result.message.text, "Hello from Gemini")

        history = view_model.chat_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[1].role, "assistant")
        self.assertEqual(history[1].provider, "gemini")
        core.stop()


class MockFallbackTests(unittest.TestCase):
    """When Gemini is unavailable or fails, MockProvider must be used automatically."""

    def test_missing_key_falls_back_to_mock_with_notice(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            registry = ProviderRegistry()
            registry.register(GeminiProvider())
            registry.register(MockProvider())
            core = _core_with_router(registry)
            view_model = _view_model(core)

            view_model.append_user_message("hello?")
            result = view_model.request_assistant_reply()

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.notice, "Gemini unavailable. Using Mock Provider.")
        self.assertEqual(result.message.provider, "mock")
        core.stop()

    def test_gemini_request_failure_falls_back_to_mock_with_notice(self) -> None:
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("temporary outage")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            with patch("iris.ai_router.providers.gemini.genai") as fake_genai:
                fake_genai.Client.return_value = client
                registry = ProviderRegistry()
                registry.register(GeminiProvider())
                registry.register(MockProvider())
                core = _core_with_router(
                    registry,
                    configuration=AIRouterConfiguration(fallback_provider="mock", max_retries=0),
                )
                view_model = _view_model(core)

                view_model.append_user_message("hello?")
                result = view_model.request_assistant_reply()

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.notice, "Gemini unavailable. Using Mock Provider.")
        self.assertEqual(result.message.provider, "mock")
        core.stop()


class ErrorHandlingTests(unittest.TestCase):
    """The ViewModel must never raise out to the UI, even when everything fails."""

    def test_no_ai_router_registered_returns_safe_result(self) -> None:
        core = IrisCore()
        core.start()
        router = core.service_registry.get("ai_router", AIRouter)
        core.service_registry.unregister("ai_router")
        view_model = _view_model(core)

        view_model.append_user_message("hello?")
        result = view_model.request_assistant_reply()

        self.assertFalse(result.used_fallback)
        self.assertEqual(result.notice, "AI Router is unavailable.")
        self.assertIn("could not reach the AI Router", result.message.text)

        # IrisCore.stop() also expects "ai_router" to be present; restore it
        # for a clean shutdown now that the test assertion is done.
        core.service_registry.register("ai_router", router)
        core.stop()

    def test_both_providers_unavailable_returns_safe_result_without_raising(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            registry = ProviderRegistry()
            registry.register(GeminiProvider())
            core = _core_with_router(registry, configuration=AIRouterConfiguration(fallback_provider="mock"))
            view_model = _view_model(core)

            # AIRouter.start() auto-discovers MockProvider even though we never
            # registered it ourselves (existing Sprint 7/8.1 behavior). To
            # genuinely exercise "everything fails", make Mock's own request
            # fail too, rather than trying to remove it from the registry.
            router = core.service_registry.get("ai_router", AIRouter)
            mock_provider = router.registry.get("mock")
            with patch.object(mock_provider, "chat", side_effect=RuntimeError("mock also down")):
                view_model.append_user_message("hello?")
                try:
                    result = view_model.request_assistant_reply()
                except Exception as exc:  # pragma: no cover - the whole point is this must not happen
                    self.fail(f"request_assistant_reply() raised instead of returning safely: {exc}")

        self.assertTrue(result.used_fallback)
        self.assertIsNotNone(result.notice)
        self.assertIn("could not reach any AI provider", result.message.text)
        core.stop()

    def test_clear_chat_empties_history(self) -> None:
        registry = ProviderRegistry()
        registry.register(MockProvider())
        core = _core_with_router(registry)
        view_model = _view_model(core)

        view_model.append_user_message("hello")
        view_model.request_assistant_reply()
        self.assertEqual(len(view_model.chat_history()), 2)

        view_model.clear_chat()
        self.assertEqual(view_model.chat_history(), [])
        core.stop()

    def test_chat_message_is_immutable(self) -> None:
        message = ChatMessage(role="user", text="hi", timestamp="12:00:00")
        with self.assertRaises(Exception):
            message.text = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
