"""Notification delivery service for IRIS."""

from __future__ import annotations

import platform
import subprocess

from iris.services.base import ManagedService
from iris.services.logger import get_logger


class NotificationManager(ManagedService):
    """Send console and desktop notifications through a future-ready interface."""

    name = "Notifications"
    version = "1.0.0"

    def __init__(self) -> None:
        super().__init__()
        self._logger = get_logger(__name__).bind(service=self.name)

    def start(self) -> None:
        """Mark the notification service as running."""
        super().start()
        self._logger.info("Notification manager started")

    def notify_console(self, title: str, message: str) -> None:
        """Send a console notification."""
        self._logger.info("Console notification: {} - {}", title, message)
        print(f"{title}: {message}")

    def notify_desktop(self, title: str, message: str) -> None:
        """Send a best-effort desktop notification."""
        if platform.system() != "Windows":
            self.notify_console(title, message)
            return

        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] | Out-Null;"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            self.notify_console(title, message)
            return

        self._logger.info("Desktop notification requested: {} - {}", title, message)

    def notify_telegram(self, title: str, message: str) -> None:
        """Placeholder for future Telegram notifications."""
        raise NotImplementedError("Telegram notifications are planned for a future sprint")

    def notify_email(self, title: str, message: str) -> None:
        """Placeholder for future email notifications."""
        raise NotImplementedError("Email notifications are planned for a future sprint")
