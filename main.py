"""Application entry point for IRIS."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from iris.config.loader import load_config
from iris.core.iris_core import IrisCore
from iris.dashboard.main_window import MainWindow
from iris.dashboard.view_model import DashboardViewModel
from iris.services.logger import configure_logger, get_log_buffer, get_logger
from iris.services.metrics import MetricsService


def main() -> int:
    """Start the IRIS desktop dashboard."""
    config = load_config()
    configure_logger(config.logging)

    logger = get_logger(__name__)
    logger.info("Starting IRIS dashboard")

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
    logger.info("IRIS dashboard stopped")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
