# IRIS Workflows

Sprint 5 adds workflow automation without redesigning earlier services or agent APIs.

## Execution Model

All orchestration follows one path:

```text
Workflow Engine
Decision Engine
Task Queue
Agent
```

Agents never call each other directly. A workflow step is queued as a `QueuedTask`. By default, the task publishes a configurable event through `EventBus`, such as `research.scan.requested` or `youtube.requested`. Tests and future integrations can register step handlers, but those handlers still execute through `TaskQueue`.

## Workflow Definition

Workflows are JSON-compatible dictionaries:

```json
{
  "name": "youtube_daily",
  "description": "Automatically generate and upload one video",
  "steps": ["research", "decision", "youtube"]
}
```

Steps can also be expanded:

```json
{
  "name": "research",
  "payload": {"region": "IN"},
  "priority": 60,
  "max_retries": 1,
  "decision_rules": {"minimum_score": 70}
}
```

YAML support remains future-ready because the engine accepts normalized dictionaries rather than depending on a JSON parser internally.

## Lifecycle

Executions use these states:

- `Queued`
- `Running`
- `Paused`
- `Waiting`
- `Completed`
- `Failed`
- `Cancelled`
- `Retrying`

The engine persists current step, completed steps, start time, finish time, duration, status, errors, retry count, and queued task ids. On restart, queued/running/waiting/retrying executions reload as `Waiting` so they can be resumed deliberately.

## Scheduler

`SchedulerService` supports:

- Manual execution
- One-time schedules
- Daily schedules
- Weekly schedules
- Monthly schedules
- Simple cron expressions
- Recurring schedules
- Delayed execution
- Timezone-aware run times
- Persistence across restart

Schedules are stored in `workflows/schedules.json`.

## Decision Engine

`DecisionEngine` is generic and reusable. Inputs include:

- Research score
- Confidence
- Duplicate detection
- Category
- User rules
- Time rules
- Retry count

Outputs are:

- `EXECUTE`
- `SKIP`
- `RETRY`
- `DELAY`
- `REJECT`

Decision events are published as `decision.made`.

## Events

Sprint 5 publishes:

- `workflow.created`
- `workflow.started`
- `workflow.step.started`
- `workflow.step.completed`
- `workflow.completed`
- `workflow.failed`
- `workflow.cancelled`
- `workflow.paused`
- `workflow.resumed`
- `scheduler.started`
- `scheduler.triggered`
- `scheduler.completed`
- `decision.made`

## Metrics

Workflow metrics include:

- Workflow count
- Success rate
- Failure rate
- Average duration
- Average retries
- Scheduler latency
- Queue wait time
