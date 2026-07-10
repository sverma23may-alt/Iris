"""Research Agent production plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from iris.agents.base_agent import BaseAgent
from iris.plugins.context import PluginContext
from iris.plugins.research_models import Topic
from iris.plugins.research_providers import TopicProvider, default_research_providers
from iris.plugins.research_scoring import TopicScoringEngine
from iris.services.event_bus import Event
from iris.services.task_queue import QueuedTask
from iris.utils.status import AgentStatus
from iris.workflows.decision_engine import DecisionInput, DecisionOutcome


@dataclass(frozen=True)
class ResearchResult:
    """Result returned by a completed research scan."""

    task_id: str
    topics_found: int
    ranked_topics: list[Topic]
    provider_status: list[dict[str, Any]]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    youtube_task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return primitive event/dashboard data."""
        return {
            "task_id": self.task_id,
            "topics_found": self.topics_found,
            "ranked_topics": [topic.to_dict() for topic in self.ranked_topics],
            "provider_status": self.provider_status,
            "created_at": self.created_at.isoformat(),
            "youtube_task_id": self.youtube_task_id,
        }


class ResearchAgent(BaseAgent):
    """Collect, score, and rank provider-based topic ideas."""

    EVENT_SCAN_REQUESTED = "research.scan.requested"
    EVENT_STOP_REQUESTED = "research.stop.requested"

    def __init__(
        self,
        context: PluginContext,
        providers: list[TopicProvider] | None = None,
        scoring_engine: TopicScoringEngine | None = None,
    ) -> None:
        super().__init__(name="Research Agent", version="1.0.0", event_bus=context.event_bus)
        self._context = context
        self._logger = context.logger.bind(plugin=self.name)
        self._providers = providers or default_research_providers(context.configuration)
        self._scoring_engine = scoring_engine or TopicScoringEngine(context.configuration)
        self._current_task_id: str | None = None
        self._current_scan = "Idle"
        self._topics_found = 0
        self._top_ranked_topics: list[Topic] = []
        self._provider_status: dict[str, dict[str, Any]] = {}
        self._recent_events: list[dict[str, Any]] = []
        self._last_scan: datetime | None = None
        self._last_result: ResearchResult | None = None
        self._stop_requested = False
        self._initialized = False
        self.initialize()

    @property
    def last_result(self) -> ResearchResult | None:
        """Return the latest research scan result."""
        return self._last_result

    def initialize(self) -> None:
        """Subscribe to research scan events."""
        if self._initialized:
            return

        self.subscribe_event(self.EVENT_SCAN_REQUESTED, self._on_scan_requested)
        self.subscribe_event(self.EVENT_STOP_REQUESTED, self._on_stop_requested)
        self._status = AgentStatus.INITIALIZED
        self._initialized = True
        self._logger.info("Research Agent initialized")

    def run(self) -> None:
        """Mark the agent as running."""
        if not self._initialized:
            self.initialize()
        self._status = AgentStatus.RUNNING

    def stop(self) -> None:
        """Request the current scan to stop and mark the agent stopped."""
        self._stop_requested = True
        self._status = AgentStatus.STOPPED

    def health(self) -> bool:
        """Return True when at least one provider is configured."""
        return bool(self._providers)

    def submit_scan(self, payload: dict[str, Any] | None = None, priority: int = 60) -> str:
        """Queue a research scan and return the IRIS task id."""
        task = QueuedTask(
            name="research.scan",
            handler=self._execute_scan,
            payload=payload or {},
            priority=priority,
            max_retries=0,
        )
        task_id = self._context.task_queue.add_task(task)
        self._logger.info("Queued research scan {}", task_id)
        return task_id

    def request_stop(self) -> None:
        """Request cancellation of the current scan."""
        self._stop_requested = True
        self._current_scan = "Stopping"

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Return dashboard-ready state for the Research page."""
        return {
            "status": self.status.value,
            "providers": [
                {
                    "name": provider.name,
                    "enabled": provider.enabled,
                    **self._provider_status.get(provider.name, {}),
                }
                for provider in self._providers
            ],
            "current_scan": self._current_scan,
            "topics_found": self._topics_found,
            "top_ranked_topics": [topic.to_dict() for topic in self._top_ranked_topics],
            "provider_status": list(self._provider_status.values()),
            "last_scan": self._last_scan.isoformat() if self._last_scan else "--",
            "recent_events": list(self._recent_events[-20:]),
        }

    async def _on_scan_requested(self, event: Event) -> None:
        task_id = self.submit_scan(event.payload)
        await self._publish(
            "research.started",
            {"task_id": task_id, "stage": "queued", "message": "Research scan queued"},
        )

    async def _on_stop_requested(self, event: Event) -> None:
        self.request_stop()
        await self._publish(
            "research.failed",
            {
                "task_id": self._current_task_id,
                "error": {"code": "scan_stopped", "message": "Research scan stop requested"},
            },
        )

    async def _execute_scan(self, task: QueuedTask) -> ResearchResult:
        self._current_task_id = task.task_id
        self._current_scan = "Running"
        self._topics_found = 0
        self._top_ranked_topics = []
        self._stop_requested = False
        self._status = AgentStatus.RUNNING
        collected_topics: list[Topic] = []

        await self._publish("research.started", {"task_id": task.task_id})
        try:
            for provider in self._providers:
                if self._stop_requested:
                    raise RuntimeError("Research scan stopped")

                if not provider.enabled:
                    self._record_provider_status(provider)
                    continue

                await self._publish(
                    "research.provider.started",
                    {"task_id": task.task_id, "provider": provider.name},
                )
                provider_topics = await provider.collect()
                self._record_provider_status(provider)

                for topic in provider_topics:
                    collected_topics.append(topic)
                    await self._publish(
                        "research.topic.discovered",
                        {"task_id": task.task_id, "provider": provider.name, "topic": topic.to_dict()},
                    )

                await self._publish(
                    "research.provider.finished",
                    {
                        "task_id": task.task_id,
                        "provider": provider.name,
                        "topics_found": len(provider_topics),
                    },
                )

            ranked_topics = self._scoring_engine.rank(collected_topics)
            max_topics = int(self._context.configuration.get("research.max_topics", 10) or 10)
            top_topics = ranked_topics[: min(10, max_topics)]
            youtube_task_id = self._maybe_queue_youtube_task(top_topics)
            result = ResearchResult(
                task_id=task.task_id,
                topics_found=len(collected_topics),
                ranked_topics=top_topics,
                provider_status=list(self._provider_status.values()),
                youtube_task_id=youtube_task_id,
            )
        except Exception as exc:
            self._status = AgentStatus.ERROR
            self._current_scan = "Failed"
            await self._publish(
                "research.failed",
                {
                    "task_id": task.task_id,
                    "error": {"code": "scan_failed", "message": str(exc)},
                },
            )
            raise

        self._last_result = result
        self._last_scan = result.created_at
        self._topics_found = result.topics_found
        self._top_ranked_topics = result.ranked_topics
        self._current_scan = "Completed"
        self._current_task_id = None
        self._status = AgentStatus.INITIALIZED
        await self._publish("research.completed", result.to_dict())
        return result

    def _record_provider_status(self, provider: TopicProvider) -> None:
        status = provider.status
        self._provider_status[provider.name] = {
            "name": status.name,
            "enabled": status.enabled,
            "healthy": status.healthy,
            "last_error": status.last_error,
            "topics_found": status.topics_found,
        }

    def _maybe_queue_youtube_task(self, topics: list[Topic]) -> str | None:
        if not topics or not self._bool_config("research.auto_create_youtube_task"):
            return None

        topic = topics[0]
        decision_engine = self._context.decision_engine
        if decision_engine is not None:
            decision = decision_engine.decide(
                DecisionInput(
                    research_score=topic.score,
                    confidence=topic.confidence,
                    duplicate_detected=bool(topic.metadata.get("duplicate_detected", False)),
                    category=topic.category,
                    user_rules=dict(self._context.configuration.get("research.decision_rules", {}) or {}),
                    time_rules=dict(self._context.configuration.get("research.time_rules", {}) or {}),
                )
            )
            self._recent_events.append(
                {
                    "name": "decision.made",
                    "payload": decision.to_dict(),
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            if decision.outcome in {DecisionOutcome.SKIP, DecisionOutcome.REJECT, DecisionOutcome.DELAY}:
                return None

        async def publish_youtube_request(task: QueuedTask) -> None:
            await self._context.event_bus.publish(
                Event(
                    "youtube.requested",
                    {
                        "research_task_id": task.payload["research_task_id"],
                        "topic": task.payload["topic"],
                    },
                    source=self.name,
                )
            )

        task = QueuedTask(
            name="research.youtube_topic_handoff",
            handler=publish_youtube_request,
            payload={
                "research_task_id": self._current_task_id,
                "topic": topic.to_dict(),
            },
            priority=70,
            max_retries=0,
        )
        return self._context.task_queue.add_task(task)

    def _bool_config(self, key: str) -> bool:
        value = self._context.configuration.get(key, False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    async def _publish(self, event_name: str, payload: dict[str, Any]) -> None:
        event = Event(event_name, payload, source=self.name)
        self._recent_events.append(
            {
                "name": event.name,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
        )
        await self.publish_event(event)
