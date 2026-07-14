"""Shared background worker for AI Router chat replies.

Both the Chat Page and the Voice Page reuse this single worker so the UI
thread never blocks on a provider call. The worker performs no chat logic of
its own: it only invokes the existing ``DashboardViewModel.request_assistant_reply``
path (which already handles AIRouter provider selection and fallback) and emits
the resulting ``ChatResult`` back to the UI thread.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal

from iris.vision.view_model import ChatResult, DashboardViewModel


class ChatReplyWorker(QThread):
    """Run a single AI Router chat reply off the UI thread."""

    reply_ready = Signal(object)  # ChatResult
    reply_error = Signal(str)

    def __init__(self, view_model: DashboardViewModel, parent: Any = None) -> None:
        super().__init__(parent)
        self._view_model = view_model

    def run(self) -> None:
        try:
            result = self._view_model.request_assistant_reply()
        except Exception as exc:  # pragma: no cover - ViewModel returns safe results
            self.reply_error.emit(str(exc))
            return
        self.reply_ready.emit(result)
