"""Research topic models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Topic:
    """Candidate topic discovered by a research provider."""

    title: str
    description: str
    source: str
    category: str
    language: str
    score: float = 0.0
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def with_score(self, score: float) -> "Topic":
        """Return a copy with an updated score."""
        return Topic(
            id=self.id,
            title=self.title,
            description=self.description,
            source=self.source,
            category=self.category,
            language=self.language,
            score=score,
            confidence=self.confidence,
            tags=list(self.tags),
            created_at=self.created_at,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a primitive representation suitable for events and UI."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "category": self.category,
            "language": self.language,
            "score": self.score,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }
