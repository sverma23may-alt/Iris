"""Configurable scoring engine for research topics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from iris.plugins.research_models import Topic
from iris.services.configuration_service import ConfigurationService


class TopicScoringEngine:
    """Score and rank topics using configurable weighted factors."""

    DEFAULT_WEIGHTS = {
        "trend": 0.25,
        "keyword_match": 0.25,
        "freshness": 0.2,
        "priority": 0.15,
        "user_preference": 0.15,
    }

    def __init__(self, configuration: ConfigurationService) -> None:
        self._configuration = configuration

    def rank(self, topics: list[Topic]) -> list[Topic]:
        """Return topics sorted by descending score."""
        scored = [topic.with_score(self.score(topic)) for topic in topics]
        minimum_score = float(self._configuration.get("research.minimum_score", 0.0) or 0.0)
        return sorted(
            [topic for topic in scored if topic.score >= minimum_score],
            key=lambda topic: (topic.score, topic.confidence, topic.created_at),
            reverse=True,
        )

    def score(self, topic: Topic) -> float:
        """Return a normalized weighted score from 0 to 100."""
        weights = self._weights()
        score = (
            self._trend(topic) * weights["trend"]
            + self._keyword_match(topic) * weights["keyword_match"]
            + self._freshness(topic) * weights["freshness"]
            + self._priority(topic) * weights["priority"]
            + self._user_preference(topic) * weights["user_preference"]
        )
        return round(max(0.0, min(100.0, score)), 2)

    def _weights(self) -> dict[str, float]:
        configured = self._configuration.get("research.scoring_weights", {})
        weights = dict(self.DEFAULT_WEIGHTS)
        if isinstance(configured, dict):
            for key in weights:
                if key in configured:
                    weights[key] = float(configured[key])

        total = sum(weights.values())
        if total <= 0:
            return dict(self.DEFAULT_WEIGHTS)
        return {key: value / total for key, value in weights.items()}

    def _trend(self, topic: Topic) -> float:
        return self._normalized(topic.metadata.get("trend_score", topic.metadata.get("trend", topic.confidence * 100)))

    def _keyword_match(self, topic: Topic) -> float:
        keywords = self._string_list("research.keywords")
        if not keywords:
            return 50.0

        searchable = " ".join([topic.title, topic.description, *topic.tags]).lower()
        matches = sum(1 for keyword in keywords if keyword.lower() in searchable)
        return min(100.0, (matches / len(keywords)) * 100.0)

    def _freshness(self, topic: Topic) -> float:
        age_hours = max(0.0, (datetime.now(UTC) - topic.created_at).total_seconds() / 3600.0)
        return max(0.0, 100.0 - min(age_hours, 168.0) / 168.0 * 100.0)

    def _priority(self, topic: Topic) -> float:
        return self._normalized(topic.metadata.get("priority", 50.0))

    def _user_preference(self, topic: Topic) -> float:
        preferred_tags = self._string_list("research.preferred_tags")
        if not preferred_tags:
            return 50.0

        topic_tags = {tag.lower() for tag in topic.tags}
        matches = sum(1 for tag in preferred_tags if tag.lower() in topic_tags)
        return min(100.0, (matches / len(preferred_tags)) * 100.0)

    def _string_list(self, key: str) -> list[str]:
        value = self._configuration.get(key, [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def _normalized(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, number))
