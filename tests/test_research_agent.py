"""Tests for Sprint 4 Research Agent."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any

from iris.plugins.context import PluginContext
from iris.plugins.research_agent import ResearchAgent
from iris.plugins.research_models import Topic
from iris.plugins.research_providers import ProviderStatus
from iris.plugins.research_scoring import TopicScoringEngine
from iris.services.background_worker import BackgroundWorker
from iris.services.configuration_service import ConfigurationService
from iris.services.event_bus import EventBus
from iris.services.logger import get_logger
from iris.services.process_manager import ProcessManager
from iris.services.service_registry import ServiceRegistry
from iris.services.task_queue import TaskQueue


class MockProvider:
    """Configurable provider test double."""

    def __init__(self, name: str, topics: list[Topic], enabled: bool = True) -> None:
        self.name = name
        self._topics = topics
        self._enabled = enabled
        self._status = ProviderStatus(name, enabled, True, topics_found=0)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def status(self) -> ProviderStatus:
        return self._status

    async def collect(self) -> list[Topic]:
        self._status = ProviderStatus(self.name, self.enabled, True, topics_found=len(self._topics))
        return self._topics


class ResearchScoringTests(unittest.TestCase):
    """Research scoring and ranking behavior."""

    def test_ranks_topics_by_configurable_weighted_score(self) -> None:
        configuration = ConfigurationService()
        configuration.set(
            "research.scoring_weights",
            {
                "trend": 0.4,
                "keyword_match": 0.3,
                "freshness": 0.1,
                "priority": 0.1,
                "user_preference": 0.1,
            },
        )
        configuration.set("research.keywords", ["ai", "automation"])
        configuration.set("research.preferred_tags", ["youtube"])
        engine = TopicScoringEngine(configuration)
        old = datetime.now(UTC) - timedelta(days=7)

        topics = [
            Topic(
                title="Gardening ideas",
                description="Seasonal planting",
                source="local",
                category="home",
                language="en",
                confidence=0.4,
                tags=["home"],
                created_at=old,
                metadata={"trend_score": 30, "priority": 20},
            ),
            Topic(
                title="AI automation for YouTube creators",
                description="Workflow automation",
                source="manual",
                category="tech",
                language="en",
                confidence=0.9,
                tags=["youtube"],
                metadata={"trend_score": 95, "priority": 90},
            ),
        ]

        ranked = engine.rank(topics)

        self.assertEqual(ranked[0].title, "AI automation for YouTube creators")
        self.assertGreater(ranked[0].score, ranked[1].score)


class ResearchAgentTests(unittest.IsolatedAsyncioTestCase):
    """Research Agent event and queue behavior."""

    async def test_scan_publishes_events_and_returns_top_ten_ranked_topics(self) -> None:
        context = self._context()
        context.configuration.set("research.max_topics", 20)
        context.configuration.set("research.minimum_score", 0)
        topics = [
            Topic(
                title=f"AI topic {index}",
                description="automation trend",
                source="mock",
                category="tech",
                language="en",
                confidence=0.8,
                tags=["ai"],
                metadata={"trend_score": 100 - index, "priority": 80},
            )
            for index in range(12)
        ]
        provider = MockProvider("mock", topics)
        events = []
        context.event_bus.subscribe("*", lambda event: events.append(event))
        agent = ResearchAgent(context, providers=[provider])
        worker = BackgroundWorker(context.task_queue, context.event_bus, poll_interval_seconds=0.05)

        agent.submit_scan()
        await worker.start()
        await self._wait_for(lambda: context.task_queue.completed_count() == 1)
        await worker.stop()

        self.assertIsNotNone(agent.last_result)
        self.assertEqual(agent.last_result.topics_found, 12)
        self.assertEqual(len(agent.last_result.ranked_topics), 10)
        event_names = {event.name for event in events}
        self.assertIn("research.started", event_names)
        self.assertIn("research.provider.started", event_names)
        self.assertIn("research.provider.finished", event_names)
        self.assertIn("research.topic.discovered", event_names)
        self.assertIn("research.completed", event_names)

    async def test_auto_youtube_handoff_uses_task_queue_and_event_bus(self) -> None:
        context = self._context()
        context.configuration.set("research.auto_create_youtube_task", True)
        topic = Topic(
            title="AI automation for creators",
            description="workflow",
            source="mock",
            category="tech",
            language="en",
            confidence=0.9,
            tags=["ai"],
            metadata={"trend_score": 95, "priority": 90},
        )
        events = []
        context.event_bus.subscribe("*", lambda event: events.append(event))
        agent = ResearchAgent(context, providers=[MockProvider("mock", [topic])])
        worker = BackgroundWorker(context.task_queue, context.event_bus, poll_interval_seconds=0.05)

        agent.submit_scan()
        await worker.start()
        await self._wait_for(lambda: context.task_queue.completed_count() == 2)
        await worker.stop()

        self.assertIsNotNone(agent.last_result)
        self.assertIsNotNone(agent.last_result.youtube_task_id)
        self.assertIn("youtube.requested", {event.name for event in events})

    async def test_provider_failure_publishes_research_failed(self) -> None:
        context = self._context()
        events = []
        context.event_bus.subscribe("*", lambda event: events.append(event))

        class FailingProvider(MockProvider):
            async def collect(self) -> list[Topic]:
                raise RuntimeError("provider unavailable")

        agent = ResearchAgent(context, providers=[FailingProvider("broken", [])])
        task_id = agent.submit_scan()
        task = context.task_queue.get_next_task()

        self.assertEqual(task.task_id, task_id)
        with self.assertRaises(RuntimeError):
            await task.handler(task)

        failed = [event for event in events if event.name == "research.failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].payload["error"]["code"], "scan_failed")

    def _context(self) -> PluginContext:
        registry = ServiceRegistry()
        event_bus = EventBus()
        task_queue = TaskQueue()
        configuration = ConfigurationService()
        return PluginContext(
            event_bus=event_bus,
            task_queue=task_queue,
            process_manager=ProcessManager(),
            configuration=configuration,
            service_registry=registry,
            logger=get_logger("test.research"),
        )

    async def _wait_for(self, predicate: Any) -> None:
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.05)
        self.fail("Timed out waiting for async condition")


if __name__ == "__main__":
    unittest.main()
