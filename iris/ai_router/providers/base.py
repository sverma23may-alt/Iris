"""Reusable provider helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from iris.ai_router.provider import AIProvider


class BaseAIProvider(AIProvider):
    """Small base class for concrete provider implementations."""

    name = "base"
    default_model = "mock-model"

    def __init__(self) -> None:
        self.last_successful_request: datetime | None = None

    def is_available(self) -> bool:
        """Return True by default for locally available provider shells."""
        return True

    def health(self) -> dict[str, Any]:
        """Return provider health details."""
        available = self.is_available()
        return {
            "name": self.name,
            "available": available,
            "status": "Online" if available else "Unavailable",
            "last_successful_request": (
                self.last_successful_request.isoformat() if self.last_successful_request else None
            ),
            "supports_streaming": self.supports_streaming(),
            "supports_images": self.supports_images(),
            "supports_reasoning": self.supports_reasoning(),
            "max_context": self.max_context(),
        }

    def estimated_cost(self, tokens_prompt: int, tokens_completion: int, model: str | None = None) -> float:
        """Return a no-cost default estimate."""
        return 0.0

    def max_context(self, model: str | None = None) -> int:
        """Return a conservative default context window."""
        return 4096

    def supports_streaming(self) -> bool:
        """Return streaming support."""
        return False

    def supports_images(self) -> bool:
        """Return image input support."""
        return False

    def supports_reasoning(self) -> bool:
        """Return reasoning control support."""
        return False

    def _mark_success(self) -> None:
        self.last_successful_request = datetime.now(UTC)
