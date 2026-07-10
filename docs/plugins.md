# IRIS Plugin Development

## PluginContext

`PluginContext` is the stable dependency injection boundary for production plugins. It exposes:

- `event_bus: EventBus`
- `task_queue: TaskQueue`
- `process_manager: ProcessManager`
- `configuration: ConfigurationService`
- `service_registry: ServiceRegistry`
- `logger`

Plugins should depend on this context instead of constructing infrastructure services directly.

## Plugin Lifecycle

Plugin files live in `iris/plugins/`. `PluginLoader` imports each plugin module, finds `BaseAgent` subclasses, and instantiates them.

Legacy plugins continue to use no-argument constructors:

```python
class LegacyAgent(BaseAgent):
    def __init__(self):
        super().__init__("Legacy Agent", "1.0.0")
```

Production plugins can request the context:

```python
class ProductionAgent(BaseAgent):
    def __init__(self, context: PluginContext):
        super().__init__("Production Agent", "1.0.0", event_bus=context.event_bus)
```

The loader automatically chooses the compatible constructor. Existing Sprint 1 and Sprint 2 plugin APIs remain valid.

## Dependency Injection

`IrisCore` builds one `PluginContext` from registry-managed services and passes it to `PluginLoader`. The context exposes stable interfaces only. Plugins should use:

- `TaskQueue` to submit work.
- `EventBus` to publish and subscribe to events.
- `ProcessManager` to launch external tools.
- `ConfigurationService` to read and persist configuration.
- `ServiceRegistry` only for stable registered service lookups.
- `logger` for contextual plugin logging.

## YouTube Agent

`YouTubeAgent` is the first production plugin. It orchestrates an existing ClipPilot installation.

Responsibilities:

- Accept YouTube work requests through `youtube.requested` events or direct `submit()` calls.
- Validate ClipPilot configuration.
- Submit work to `TaskQueue`.
- Launch ClipPilot with `ProcessManager`.
- Monitor stdout, stderr, completion, timeout, and crash states.
- Publish structured events:
  - `youtube.started`
  - `youtube.progress`
  - `youtube.completed`
  - `youtube.failed`
  - `youtube.cancelled`
- Provide dashboard state through `dashboard_snapshot()`.

Configuration keys:

- `youtube.clip_pilot_path`
- `youtube.python_executable`
- `youtube.workspace`
- `youtube.timeout_seconds`
- `youtube.auto_upload`

ClipPilot remains an external engine. IRIS does not contain video-generation logic and does not reimplement ClipPilot.

## Research Agent

`ResearchAgent` is the Sprint 4 provider-based research plugin. It uses `PluginContext`, inherits `BaseAgent`, and keeps all research inputs provider-driven.

The agent:

- Queues scans through `TaskQueue`.
- Collects topics from enabled providers.
- Publishes provider and topic events through `EventBus`.
- Scores topics with `TopicScoringEngine`.
- Returns the top 10 ranked topics.
- Optionally queues a YouTube handoff task that publishes `youtube.requested`.

It does not call OpenAI, Claude, or any LLM service.

### Topic Model

Providers return `Topic` dataclasses with:

- `id`
- `title`
- `description`
- `source`
- `category`
- `language`
- `score`
- `confidence`
- `tags`
- `created_at`
- `metadata`

### Provider Interface

Providers implement `TopicProvider`:

```python
class TopicProvider(ABC):
    name: str

    @property
    def enabled(self) -> bool:
        ...

    @property
    def status(self) -> ProviderStatus:
        ...

    async def collect(self) -> list[Topic]:
        ...
```

Built-in providers:

- `GoogleTrendsProvider`: placeholder boundary.
- `RSSFeedProvider`: reads configured RSS feed URLs or local RSS files.
- `YouTubeTrendingProvider`: placeholder boundary.
- `LocalTopicProvider`: reads configured local topics.
- `ManualTopicProvider`: reads manually supplied topics.

Providers are enabled with `research.providers`, using either a mapping or list:

```json
{
  "research.providers": {
    "rss": true,
    "local": true,
    "manual": true,
    "google_trends": false,
    "youtube_trending": false
  }
}
```

### Scoring

`TopicScoringEngine` ranks topics with configurable weights:

- trend
- keyword match
- freshness
- priority
- user preference

Optional configuration:

- `research.scoring_weights`
- `research.keywords`
- `research.preferred_tags`
- `research.minimum_score`
- `research.max_topics`
