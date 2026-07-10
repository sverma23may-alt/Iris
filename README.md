# IRIS

IRIS is a production-oriented AI orchestration platform built incrementally with Clean Architecture principles. Sprint 5 adds workflow automation, scheduling, persistence, and a generic decision engine while preserving all Sprint 1 through Sprint 4 APIs.

## Run

```powershell
python main.py
```

If `python` is not on PATH, activate or repair the project virtual environment first.

## Architecture

The application is organized around a small core, service layer, agent layer, and PySide6 dashboard. `IrisCore` remains the composition root and retrieves infrastructure through `ServiceRegistry`. The dashboard uses a view model so UI code displays state without owning business or infrastructure logic.

Production plugins receive dependencies through `PluginContext`, a stable boundary that exposes `EventBus`, `TaskQueue`, `ProcessManager`, `ConfigurationService`, `ServiceRegistry`, and a contextual logger. Legacy plugins that inherit from `BaseAgent` and use no-argument constructors continue to load unchanged.

## Sprint 1

- `IrisCore` lifecycle: `start()`, `stop()`, `register_agent()`, `unregister_agent()`, `get_status()`
- `BaseAgent` abstraction
- `AgentManager`
- Loguru logging
- dotenv configuration loader
- Basic PySide6 dashboard

## Sprint 2

- FIFO and priority task queue
- In-process event bus for agent communication
- Async background worker
- Plugin discovery from `iris/plugins/`
- Live dashboard metrics, status bar, and log panel

## Sprint 2.5 Core System Services

### Configuration Service

Centralized configuration manager with `.env` and `config.json` support. It exposes `get()`, `set()`, `save()`, `reload()`, and `validate()`. YAML support is represented by a future-ready boundary.

### Process Manager

Async external process supervisor. It can launch processes, monitor status, capture stdout and stderr, restart crashed processes, stop or kill processes, and detect timeouts. It is designed for future ClipPilot, FFmpeg, Python script, and local model execution.

### Storage Manager

Creates and returns absolute paths for managed folders:

- `videos/`
- `logs/`
- `cache/`
- `downloads/`
- `exports/`
- `temp/`
- `plugins/`

### Secrets Manager

Reads API keys, OAuth tokens, refresh tokens, and future LLM keys from `.env` and environment variables. The write boundary is intentionally future-ready for encrypted storage.

### Notification Manager

Supports console notifications and best-effort desktop notification requests. Telegram and email notifications are future extension points.

### Service Registry

Registers and retrieves services by name. `IrisCore` uses the registry to access core infrastructure, preserving dependency injection and avoiding direct UI coupling.

## Sprint 3 YouTube Agent

The YouTube Agent is the first production plugin. It integrates with an existing ClipPilot installation instead of replacing or reimplementing it. IRIS remains the orchestrator: it validates configuration, accepts YouTube tasks, queues work through `TaskQueue`, launches ClipPilot through `ProcessManager`, monitors stdout/stderr, publishes events through `EventBus`, and exposes dashboard state.

Configuration is stored through `ConfigurationService`:

- `youtube.clip_pilot_path`
- `youtube.python_executable`
- `youtube.workspace`
- `youtube.timeout_seconds`
- `youtube.auto_upload`

The agent publishes:

- `youtube.started`
- `youtube.progress`
- `youtube.completed`
- `youtube.failed`
- `youtube.cancelled`

See `docs/plugins.md` for plugin development details.

## Sprint 4 Research Agent

The Research Agent is a provider-based plugin for collecting and ranking topic ideas. It does not call LLMs and does not perform reasoning through external AI systems. Each provider is independent and can be enabled or disabled through `ConfigurationService`.

Built-in providers:

- Google Trends placeholder
- RSS feed provider
- YouTube Trending placeholder
- Local topic provider
- Manual topic provider

Configuration keys:

- `research.providers`
- `research.interval`
- `research.language`
- `research.max_topics`
- `research.minimum_score`

Additional optional keys include `research.scoring_weights`, `research.keywords`, `research.preferred_tags`, `research.rss_feeds`, `research.local_topics`, `research.manual_topics`, and `research.auto_create_youtube_task`.

The agent publishes:

- `research.started`
- `research.provider.started`
- `research.provider.finished`
- `research.topic.discovered`
- `research.completed`
- `research.failed`

When enabled, the top ranked topic can create a queue task that publishes `youtube.requested`. The Research Agent does not directly invoke the YouTube Agent.

## Sprint 5 Workflow Engine and Scheduler

Sprint 5 turns IRIS into a workflow automation platform. Workflows are JSON definitions with ordered steps, persisted executions, resumable state, generic decisions, and scheduler support.

The execution path is always:

```text
Workflow Engine
Decision Engine
Task Queue
Agent
```

Agents never call each other directly. Workflow steps are queued as `QueuedTask` instances. A default step handler publishes configurable workflow step request events, and production steps can register task-queue handlers without coupling agents together.

New services:

- `WorkflowEngine`
- `SchedulerService`
- `DecisionEngine`

Workflow execution states:

- `Queued`
- `Running`
- `Paused`
- `Waiting`
- `Completed`
- `Failed`
- `Cancelled`
- `Retrying`

The scheduler supports manual execution, one-time schedules, daily, weekly, monthly, simple cron expressions, delayed execution, recurring execution, timezone-aware run times, and persisted schedules that survive restart.

Workflow persistence stores workflow id, execution id, current step, completed steps, start time, finish time, duration, status, errors, retry count, and task ids through `StorageManager`.

See `docs/workflows.md` for lifecycle, examples, scheduler details, and persistence notes.

## Dashboard

The dashboard includes an `Overview` page and a `System Services` page. The services page displays:

- Configuration
- Storage
- Secrets
- Process Manager
- Notifications
- Service Registry

Sprint 3 also adds a `YouTube Agent` page with current status, current task, ClipPilot process state, render/upload progress, recent events, last generated video, and last upload URL.

Sprint 4 adds a `Research` page with providers, current scan, topics found, ranked topics, provider status, last scan, and scan controls.

Sprint 5 adds `Workflows`, `Scheduler`, and `Execution History` pages with workflow state, progress, upcoming schedules, last execution, metrics, and run/pause/resume/retry/cancel controls.

Each row shows status, health, and version.

## Tests

```powershell
python -m unittest discover tests
```
