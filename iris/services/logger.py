"""Loguru-backed logging service."""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger

from iris.config.loader import LoggingConfig


class LogBuffer:
    """Thread-safe in-memory log buffer for dashboard streaming."""

    def __init__(self, max_lines: int = 500) -> None:
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._lock = Lock()

    def write(self, message: str) -> None:
        """Append a formatted log line."""
        line = message.strip()
        if not line:
            return

        with self._lock:
            self._lines.append(line)

    def lines(self) -> list[str]:
        """Return buffered log lines."""
        with self._lock:
            return list(self._lines)


_log_buffer = LogBuffer()


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
    logger.add(
        _log_buffer.write,
        level=config.level.upper(),
        format="{time:HH:mm:ss} | {level} | {message}",
        backtrace=False,
        diagnose=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a contextual Loguru logger."""
    if name is None:
        return logger

    return logger.bind(name=name)


def get_log_buffer() -> LogBuffer:
    """Return the dashboard log buffer."""
    return _log_buffer
