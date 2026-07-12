"""Application entry point for IRIS."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from iris.config.loader import load_config
from iris.core.iris_core import IrisCore
from iris.vision.main_window import MainWindow
from iris.vision.view_model import DashboardViewModel
from iris.services.logger import configure_logger, get_log_buffer, get_logger
from iris.services.metrics import MetricsService


def main() -> int:
    """Start the IRIS Vision desktop UI."""
    config = load_config()
    configure_logger(config.logging)

    logger = get_logger(__name__)
    logger.info("Starting IRIS Vision")

    core = IrisCore()
    core.start()

    app = QApplication(sys.argv)
    view_model = DashboardViewModel(
        core=core,
        metrics_service=MetricsService(),
        log_buffer=get_log_buffer(),
    )
    window = MainWindow(view_model=view_model)
    window.show()

    exit_code = app.exec()
    core.stop()
    logger.info("IRIS Vision stopped")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
