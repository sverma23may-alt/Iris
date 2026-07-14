"""Google Gemini provider backed by the official google-genai SDK."""

from __future__ import annotations

import os
import time
from typing import Any

from iris.ai_router.providers.base import BaseAIProvider
from iris.ai_router.response import AIResponse

try:  # pragma: no cover - optional dependency guarded at import time
    from google import genai
except ImportError:  # pragma: no cover - exercised when the SDK is not installed
    genai = None


class GeminiProvider(BaseAIProvider):
    """Real Gemini provider. Reports Unavailable when no API key is configured."""

    name = "gemini"
    default_model = "gemini-2.5-flash"
    default_embedding_model = "gemini-embedding-001"

    _API_KEY_ENV = "GEMINI_API_KEY"
    _CONTEXT_WINDOWS = {
        "gemini-2.5-flash": 1_048_576,
        "gemini-2.5-pro": 1_048_576,
        "gemini-2.5-flash-lite": 1_048_576,
    }
    _DEFAULT_CONTEXT_WINDOW = 1_048_576

    def __init__(self) -> None:
        super().__init__()
        # Reads from the process environment, which iris.services.secrets_manager
        # already populates from .env via python-dotenv. No new configuration
        # system is introduced here.
        self._api_key = os.environ.get(self._API_KEY_ENV) or None
        self._client: Any | None = None
        if self._api_key and genai is not None:
            try:
                self._client = genai.Client(api_key=self._api_key)
            except Exception:
                # Client construction failing (e.g. malformed key) must not raise
                # out of __init__; the provider simply stays unavailable.
                self._client = None

    def is_available(self) -> bool:
        """Return True only when the SDK is installed, a key is configured, and the client initialized."""
        return genai is not None and bool(self._api_key) and self._client is not None

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Execute a chat request against Gemini."""
        prompt_text = self._flatten_messages(messages)
        return self._generate(model, prompt_text, prompt_text)

    def complete(self, prompt: str, model: str | None = None, **kwargs: Any) -> AIResponse:
        """Execute a text completion request against Gemini."""
        return self._generate(model, prompt, prompt)

    def embed(self, text: str | list[str], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Create embeddings through Gemini."""
        self._require_client()
        values = text if isinstance(text, list) else [text]
        resolved_model = model or self.default_embedding_model
        started = time.perf_counter()
        try:
            result = self._client.models.embed_content(model=resolved_model, contents=values)
        except Exception as exc:
            raise RuntimeError(self._safe_error(exc)) from None
        latency = (time.perf_counter() - started) * 1000.0
        embeddings = [list(embedding.values or []) for embedding in (result.embeddings or [])]
        self._mark_success()
        return AIResponse(
            provider=self.name,
            model=resolved_model,
            response=embeddings,
            latency_ms=round(latency, 3),
            estimated_cost=self.estimated_cost(0, 0, resolved_model),
            tokens_prompt=0,
            tokens_completion=0,
            total_tokens=0,
            success=True,
            metadata={},
        )

    def vision(self, prompt: str, images: list[Any], model: str | None = None, **kwargs: Any) -> AIResponse:
        """Execute a vision-capable request against Gemini."""
        self._require_client()
        contents = [prompt, *images]
        return self._generate(model, contents, prompt)

    def supports_streaming(self) -> bool:
        """Gemini's SDK supports streaming responses."""
        return True

    def supports_images(self) -> bool:
        """Gemini's SDK supports image inputs."""
        return True

    def supports_reasoning(self) -> bool:
        """Gemini 2.5 models support thinking/reasoning controls."""
        return True

    def max_context(self, model: str | None = None) -> int:
        """Return the context window for the selected (or default) model."""
        return self._CONTEXT_WINDOWS.get(model or self.default_model, self._DEFAULT_CONTEXT_WINDOW)

    def estimated_cost(self, tokens_prompt: int, tokens_completion: int, model: str | None = None) -> float:
        """Return a conservative cost estimate.

        Real per-token Gemini pricing is not wired up yet; this is a placeholder
        hook so AIRouter's cost_saving routing mode has a value to compare
        against other providers. It intentionally never raises.
        """
        return 0.0

    def _require_client(self) -> None:
        if not self.is_available():
            raise RuntimeError("Gemini provider is unavailable: missing API key or SDK not installed")

    def _generate(self, model: str | None, contents: Any, prompt_text: str) -> AIResponse:
        self._require_client()
        resolved_model = model or self.default_model
        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(model=resolved_model, contents=contents)
        except Exception as exc:
            raise RuntimeError(self._safe_error(exc)) from None
        latency = (time.perf_counter() - started) * 1000.0
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
        completion_tokens = getattr(usage, "candidates_token_count", None) or 0
        total_tokens = getattr(usage, "total_token_count", None) or (prompt_tokens + completion_tokens)
        self._mark_success()
        return AIResponse(
            provider=self.name,
            model=resolved_model,
            response=response.text,
            latency_ms=round(latency, 3),
            estimated_cost=self.estimated_cost(prompt_tokens, completion_tokens, resolved_model),
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
            total_tokens=total_tokens,
            success=True,
            metadata={},
        )

    def _safe_error(self, exc: Exception) -> str:
        """Return an error message that can never contain the configured API key."""
        message = f"Gemini request failed: {exc}"
        if self._api_key and self._api_key in message:
            message = message.replace(self._api_key, "***redacted***")
        return message

    @staticmethod
    def _flatten_messages(messages: list[dict[str, Any]]) -> str:
        return "\n".join(str(message.get("content", "")) for message in messages)
