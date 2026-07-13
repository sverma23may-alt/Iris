"""Standard AI Router response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AIResponse:
    """Provider-neutral response returned by every AI Router request."""

    provider: str
    model: str
    response: Any
    latency_ms: float
    estimated_cost: float
    tokens_prompt: int
    tokens_completion: int
    total_tokens: int
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a primitive dashboard/test representation."""
        return {
            "provider": self.provider,
            "model": self.model,
            "response": self.response,
            "latency_ms": self.latency_ms,
            "estimated_cost": self.estimated_cost,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "total_tokens": self.total_tokens,
            "success": self.success,
            "error": self.error,
            "metadata": dict(self.metadata),
        }
