"""Provider interfaces and provider implementations for ResearchAgent."""

from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from iris.plugins.research_models import Topic
from iris.services.configuration_service import ConfigurationService


@dataclass(frozen=True)
class ProviderStatus:
    """Read-only provider status for dashboard reporting."""

    name: str
    enabled: bool
    healthy: bool
    last_error: str | None = None
    topics_found: int = 0


class TopicProvider(ABC):
    """Contract implemented by independent topic providers."""

    name: str

    def __init__(self, configuration: ConfigurationService) -> None:
        self._configuration = configuration
        self._last_status = ProviderStatus(self.name, self.enabled, True)

    @property
    def enabled(self) -> bool:
        """Return True when this provider is enabled in configuration."""
        providers = self._configuration.get("research.providers", {})
        if isinstance(providers, dict):
            return self._bool_value(providers.get(self.name, False))
        if isinstance(providers, list):
            return self.name in providers
        return False

    @property
    def status(self) -> ProviderStatus:
        """Return the latest provider status."""
        return self._last_status

    async def collect(self) -> list[Topic]:
        """Collect topics when enabled and update provider status."""
        if not self.enabled:
            self._last_status = ProviderStatus(self.name, False, True, topics_found=0)
            return []

        try:
            topics = await self._collect_enabled()
        except Exception as exc:
            self._last_status = ProviderStatus(self.name, True, False, last_error=str(exc))
            raise

        self._last_status = ProviderStatus(
            self.name,
            True,
            True,
            topics_found=len(topics),
        )
        return topics

    @abstractmethod
    async def _collect_enabled(self) -> list[Topic]:
        """Collect topics for an enabled provider."""

    def _language(self) -> str:
        return str(self._configuration.get("research.language", "en"))

    def _bool_value(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


class GoogleTrendsProvider(TopicProvider):
    """Placeholder boundary for future Google Trends integration."""

    name = "google_trends"

    async def _collect_enabled(self) -> list[Topic]:
        return []


class YouTubeTrendingProvider(TopicProvider):
    """Placeholder boundary for future YouTube Trending integration."""

    name = "youtube_trending"

    async def _collect_enabled(self) -> list[Topic]:
        return []


class RSSFeedProvider(TopicProvider):
    """Collect topics from configured RSS feed URLs or local RSS files."""

    name = "rss"

    async def _collect_enabled(self) -> list[Topic]:
        urls = self._configuration.get("research.rss_feeds", [])
        if not isinstance(urls, list):
            raise ValueError("research.rss_feeds must be a list")

        topics: list[Topic] = []
        for url in urls:
            if not isinstance(url, str):
                continue
            topics.extend(self._topics_from_feed(url))
        return topics

    def _topics_from_feed(self, url: str) -> list[Topic]:
        content = self._read_feed(url)
        root = ET.fromstring(content)
        topics: list[Topic] = []

        for item in root.findall(".//item"):
            title = self._child_text(item, "title")
            if not title:
                continue

            description = self._child_text(item, "description")
            category = self._child_text(item, "category") or "news"
            tags = [category] if category else []
            published = self._parse_date(self._child_text(item, "pubDate"))
            topics.append(
                Topic(
                    title=title,
                    description=description,
                    source="rss",
                    category=category,
                    language=self._language(),
                    confidence=0.7,
                    tags=tags,
                    created_at=published,
                    metadata={"feed": url, "link": self._child_text(item, "link")},
                )
            )
        return topics

    def _read_feed(self, url: str) -> bytes:
        path = Path(url)
        if path.exists():
            return path.read_bytes()

        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read()

    def _child_text(self, item: ET.Element, name: str) -> str:
        child = item.find(name)
        if child is None or child.text is None:
            return ""
        return child.text.strip()

    def _parse_date(self, value: str) -> datetime:
        if not value:
            return datetime.now(UTC)

        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return datetime.now(UTC)

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)


class LocalTopicProvider(TopicProvider):
    """Collect topics from configured local topic records."""

    name = "local"

    async def _collect_enabled(self) -> list[Topic]:
        records = self._configuration.get("research.local_topics", [])
        return self._topics_from_records(records, "local")

    def _topics_from_records(self, records: Any, source: str) -> list[Topic]:
        if not isinstance(records, list):
            raise ValueError(f"research.{source}_topics must be a list")

        topics: list[Topic] = []
        for record in records:
            if isinstance(record, str):
                topics.append(
                    Topic(
                        title=record,
                        description="",
                        source=source,
                        category="general",
                        language=self._language(),
                        confidence=0.6,
                    )
                )
                continue

            if not isinstance(record, dict) or not record.get("title"):
                continue

            topics.append(
                Topic(
                    title=str(record["title"]),
                    description=str(record.get("description", "")),
                    source=source,
                    category=str(record.get("category", "general")),
                    language=str(record.get("language", self._language())),
                    confidence=float(record.get("confidence", 0.6)),
                    tags=[str(tag) for tag in record.get("tags", [])],
                    metadata=dict(record.get("metadata", {})),
                )
            )
        return topics


class ManualTopicProvider(LocalTopicProvider):
    """Collect manually supplied topics from configuration."""

    name = "manual"

    async def _collect_enabled(self) -> list[Topic]:
        records = self._configuration.get("research.manual_topics", [])
        return self._topics_from_records(records, "manual")


def default_research_providers(configuration: ConfigurationService) -> list[TopicProvider]:
    """Return the built-in provider set."""
    return [
        GoogleTrendsProvider(configuration),
        RSSFeedProvider(configuration),
        YouTubeTrendingProvider(configuration),
        LocalTopicProvider(configuration),
        ManualTopicProvider(configuration),
    ]
