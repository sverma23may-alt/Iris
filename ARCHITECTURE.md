# IRIS Architecture

IRIS is organized as a small composition root, stable service layer, plugin/agent layer, and PySide6 dashboard.

## Composition Root

`IrisCore` owns application startup and shutdown. It creates and registers core services in `ServiceRegistry`, starts managed services, starts the async task worker, discovers plugins, and exposes status snapshots to the dashboard.

## Services

Core infrastructure lives under `iris/services/`:

- `EventBus` provides in-process publish/subscribe messaging.
- `TaskQueue` owns queued work and task lifecycle state.
- `BackgroundWorker` executes queued task handlers asynchronously.
- `ProcessManager` launches and monitors external processes.
- `ConfigurationService` loads and persists configuration values.
- `StorageManager`, `SecretsManager`, and `NotificationManager` provide platform boundaries for storage, secrets, and notifications.
- `ServiceRegistry` is the dependency lookup boundary.

Managed services expose health through a stable `ManagedService` contract.

## Workflow Automation

Sprint 5 adds `iris/workflows/` as the orchestration layer:

- `WorkflowEngine` owns workflow definitions, execution state, persistence, pause/resume/retry/cancel, dashboard snapshots, and workflow metrics.
- `DecisionEngine` is generic and reusable by current and future agents. It accepts research score, confidence, duplicate detection, category, user rules, time rules, and retry count. It returns `EXECUTE`, `SKIP`, `RETRY`, `DELAY`, or `REJECT`.
- `SchedulerService` persists one-time, delayed, daily, weekly, monthly, recurring, timezone-aware, and simple cron schedules.

The required execution path is:

```text
WorkflowEngine -> DecisionEngine -> TaskQueue -> Agent
```

Agents never invoke each other directly. Workflow steps become `QueuedTask` instances. The default workflow step handler emits configured events through `EventBus`; custom step handlers are still task-queue handlers, not agent calls.

Workflow state is persisted through `StorageManager` under the `workflows` namespace:

- `definitions.json`
- `executions.json`
- `schedules.json`

On startup, `IrisCore` registers `workflow_engine`, `scheduler`, and `decision_engine`, exposes them through `PluginContext`, and reloads persisted workflow definitions and resumable executions.

## Plugins and Agents

All agents inherit from `BaseAgent`. Sprint 3 keeps the original no-argument plugin constructor style and adds a context-aware style:

```python
class MyAgent(BaseAgent):
    ...
```

```python
class MyAgent(BaseAgent):
    def __init__(self, context: PluginContext):
        ...
```

`PluginLoader` detects constructor compatibility automatically. Context-aware plugins receive only stable dependencies through `PluginContext`; they do not receive internal core objects.

## Dashboard

The dashboard is read-only from an infrastructure perspective. `DashboardViewModel` adapts `IrisCore` and registered agents into display state. `MainWindow` renders that state and does not own process, queue, or plugin logic.

## Sprint 3 Boundary

The YouTube Agent integrates with ClipPilot as an external engine. IRIS does not generate videos and does not duplicate ClipPilot behavior. It queues work, launches ClipPilot, monitors process output, emits events, and displays state.

## Sprint 4 Research Boundary

The Research Agent is an additive production plugin. It uses `PluginContext` and does not modify YouTube Agent or Process Manager APIs.

Research is provider-based:

- Providers implement a common `TopicProvider` interface.
- Providers can be enabled or disabled through `ConfigurationService`.
- Provider implementations collect topic candidates and return `Topic` dataclasses.
- The scoring engine ranks provider output with configurable weights.

The Research Agent publishes scan and provider events through `EventBus`, executes scans through `TaskQueue`, and exposes dashboard state through `dashboard_snapshot()`.

The optional YouTube handoff remains decoupled. Research creates a queued handoff task that publishes `youtube.requested`; it does not import, instantiate, or directly call `YouTubeAgent`.

Sprint 5 routes the Research Agent's optional YouTube handoff through the generic `DecisionEngine` before it queues the event-publishing handoff task.

No LLM reasoning is part of Sprint 4. Research inputs come only from configured providers.
