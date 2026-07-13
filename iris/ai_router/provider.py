"""AI Router provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from iris.ai_router.response import AIResponse


class AIProvider(ABC):
    """Common provider contract for all future AI integrations."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider can accept requests."""

    @abstractmethod
    def chat(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Execute a chat request."""

    @abstractmethod
    def complete(self, prompt: str, model: str | None = None, **kwargs: Any) -> AIResponse:
        """Execute a text completion request."""

    @abstractmethod
    def embed(self, text: str | list[str], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Create embeddings."""

    @abstractmethod
    def vision(self, prompt: str, images: list[Any], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Execute a vision-capable request."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return provider health details."""

    @abstractmethod
    def estimated_cost(self, tokens_prompt: int, tokens_completion: int, model: str | None = None) -> float:
        """Estimate request cost."""

    @abstractmethod
    def max_context(self, model: str | None = None) -> int:
        """Return the maximum context length for the selected model."""

    @abstractmethod
    def supports_streaming(self) -> bool:
        """Return True when streaming responses are supported."""

    @abstractmethod
    def supports_images(self) -> bool:
        """Return True when image inputs are supported."""

    @abstractmethod
    def supports_reasoning(self) -> bool:
        """Return True when reasoning controls are supported."""
