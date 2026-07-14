"""Sprint 8.3 Voice Page unit and integration tests.

The Voice Page reuses the existing DashboardViewModel chat path and the shared
ChatReplyWorker. UI-dependent tests use Qt with the offscreen platform so they
run without a display; they mirror the existing suite's mocking conventions
(no live network calls). All Gemini calls are mocked/unavailable.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from iris.ai_router.configuration import AIRouterConfiguration
from iris.ai_router.providers.gemini import GeminiProvider
from iris.ai_router.providers.mock import MockProvider
from iris.ai_router.registry import ProviderRegistry
from iris.ai_router.router import AIRouter
from iris.core.iris_core import IrisCore
from iris.services.logger import LogBuffer
from iris.services.metrics import MetricsService
from iris.vision.view_model import DashboardViewModel


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication(sys.argv)


def _core_with_router() -> IrisCore:
    """Real IrisCore whose AIRouter has Gemini (unavailable) + Mock providers."""
    core = IrisCore()
    registry = ProviderRegistry()
    registry.register(GeminiProvider())  # no API key -> unavailable
    registry.register(MockProvider())
    configuration = AIRouterConfiguration(fallback_provider="mock", max_retries=0)
    router = AIRouter(configuration=configuration, registry=registry)
    core.service_registry.register("ai_router", router)
    core.start()
    return core


class SharedHistoryTests(unittest.TestCase):
    """Voice shares the exact chat history used by the Chat Page."""

    def test_append_then_reply_populates_shared_history(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            core = _core_with_router()
        view_model = DashboardViewModel(core=core, metrics_service=MetricsService(), log_buffer=LogBuffer(200))
        view_model.append_user_message("hello voice")
        result = view_model.request_assistant_reply()
        history = view_model.chat_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[1].role, "assistant")
        self.assertEqual(history[1].provider, "mock")
        self.assertEqual(history[1].timestamp, result.message.timestamp)
        self.assertTrue(result.used_fallback)
        core.stop()

    def test_clear_chat_empties_shared_history(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            core = _core_with_router()
        view_model = DashboardViewModel(core=core, metrics_service=MetricsService(), log_buffer=LogBuffer(200))
        view_model.append_user_message("one")
        view_model.request_assistant_reply()
        self.assertEqual(len(view_model.chat_history()), 2)
        view_model.clear_chat()
        self.assertEqual(view_model.chat_history(), [])
        core.stop()


class VoiceFallbackIntegrationTests(unittest.TestCase):
    """Gemini unavailable -> AIRouter fallback -> MockProvider -> Voice display."""

    def test_voice_page_displays_mock_reply_after_fallback(self) -> None:
        from iris.vision.main_window import MainWindow

        _app()
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            core = _core_with_router()
        view_model = DashboardViewModel(core=core, metrics_service=MetricsService(), log_buffer=LogBuffer(200))
        window = MainWindow(view_model=view_model)

        window._voice_input.setText("Are you there?")
        window._send_voice_message()

        worker = window._voice_worker
        self.assertIsNotNone(worker)
        spy = QSignalSpy(worker.reply_ready)
        self.assertTrue(spy.wait(5000), "Voice reply worker did not emit within timeout")

        history_text = window._voice_history.toPlainText()
        badge_text = window._voice_badge.text() if window._voice_badge is not None else ""

        self.assertIn("Are you there?", history_text)
        self.assertIn("Mock chat response", history_text)
        self.assertIn("mock", badge_text.lower())
        self.assertIn("(fallback)", badge_text.lower())
        if window._voice_core is not None:
            self.assertEqual(window._voice_core.state, "speaking")
        core.stop()


if __name__ == "__main__":
    unittest.main()
