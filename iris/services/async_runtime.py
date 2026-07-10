"""Dedicated asyncio runtime hosted in a background thread."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from threading import Thread
from typing import Any, Coroutine


class AsyncRuntime:
    """Run async infrastructure without blocking the Qt event loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop
        self._thread: Thread
        self._started = False
        self._create_runtime()

    def start(self) -> None:
        """Start the runtime thread."""
        if self._started:
            return

        if self._loop.is_closed():
            self._create_runtime()

        self._thread.start()
        self._started = True

    def stop(self) -> None:
        """Stop the runtime thread."""
        if not self._started:
            return

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()
        self._started = False

    def submit(self, coroutine: Coroutine[Any, Any, Any]) -> Future[Any]:
        """Schedule a coroutine on the runtime event loop."""
        if not self._started:
            raise RuntimeError("Async runtime is not started")

        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _create_runtime(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run_loop, name="iris-async-runtime", daemon=True)
