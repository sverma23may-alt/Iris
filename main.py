"""Application entry point for IRIS Sprint 1."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from iris.config.loader import load_config
from iris.core.iris_core import IrisCore
from iris.dashboard.main_window import MainWindow
from iris.services.logger import configure_logger, get_logger


def main() -> int:
    """Start the IRIS desktop dashboard."""
    config = load_config()
    configure_logger(config.logging)

    logger = get_logger(__name__)
    logger.info("Starting IRIS dashboard")

    core = IrisCore()
    core.start()

    app = QApplication(sys.argv)
    window = MainWindow(core=core)
    window.show()

    exit_code = app.exec()
    core.stop()
    logger.info("IRIS dashboard stopped")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
