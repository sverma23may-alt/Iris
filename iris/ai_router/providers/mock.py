"""Mock AI provider used for Sprint 7 architecture tests."""

from __future__ import annotations

import time
from typing import Any

from iris.ai_router.providers.base import BaseAIProvider
from iris.ai_router.response import AIResponse


class MockProvider(BaseAIProvider):
    """Provider that returns deterministic fake responses without API keys."""

    name = "mock"
    default_model = "mock-router-001"

    def __init__(self, available: bool = True, latency_ms: float = 5.0) -> None:
        super().__init__()
        self._available = available
        self._latency_ms = latency_ms

    def is_available(self) -> bool:
        """Return configured availability."""
        return self._available

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Return a fake chat response."""
        text = " ".join(str(message.get("content", "")) for message in messages)
        return self._response(model, f"Mock chat response: {text}".strip(), text)

    def complete(self, prompt: str, model: str | None = None, **kwargs: Any) -> AIResponse:
        """Return a fake completion response."""
        return self._response(model, f"Mock completion: {prompt}".strip(), prompt)

    def embed(self, text: str | list[str], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Return fake embeddings."""
        values = text if isinstance(text, list) else [text]
        embeddings = [[float((index + offset) % 7) / 7.0 for offset in range(8)] for index, _ in enumerate(values)]
        return self._response(model, embeddings, " ".join(values), completion_tokens=0)

    def vision(self, prompt: str, images: list[Any], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Return a fake vision response."""
        return self._response(model, f"Mock vision response for {len(images)} image(s): {prompt}", prompt)

    def supports_images(self) -> bool:
        """Mock provider accepts fake image requests."""
        return True

    def _response(
        self,
        model: str | None,
        response: Any,
        prompt_text: str,
        completion_tokens: int | None = None,
    ) -> AIResponse:
        started = time.perf_counter()
        if self._latency_ms:
            time.sleep(self._latency_ms / 1000.0)
        prompt_tokens = _token_count(prompt_text)
        response_text = str(response)
        output_tokens = _token_count(response_text) if completion_tokens is None else completion_tokens
        latency = (time.perf_counter() - started) * 1000.0
        self._mark_success()
        return AIResponse(
            provider=self.name,
            model=model or self.default_model,
            response=response,
            latency_ms=round(latency, 3),
            estimated_cost=self.estimated_cost(prompt_tokens, output_tokens, model),
            tokens_prompt=prompt_tokens,
            tokens_completion=output_tokens,
            total_tokens=prompt_tokens + output_tokens,
            success=True,
            metadata={"mock": True},
        )


def _token_count(text: str) -> int:
    return len([part for part in text.split() if part])
