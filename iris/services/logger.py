"""Loguru-backed logging service."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger

from iris.config.loader import LoggingConfig


def configure_logger(config: LoggingConfig) -> None:
    """Configure application logging sinks."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=config.level.upper(),
        backtrace=False,
        diagnose=False,
    )

    log_path = Path(config.file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=config.level.upper(),
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        backtrace=False,
        diagnose=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a contextual Loguru logger."""
    if name is None:
        return logger

    return logger.bind(name=name)
