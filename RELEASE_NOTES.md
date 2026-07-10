# IRIS Release Notes

## 0.5.0 - Sprint 5 Workflow Engine and Scheduler

- Added `iris.workflows` with workflow domain models, `WorkflowEngine`, `DecisionEngine`, and `SchedulerService`.
- Added JSON workflow definitions with future-ready normalized loading for YAML support.
- Added persisted workflow definitions, executions, and schedules through `StorageManager`.
- Added pause, resume, retry, cancel, restart-resume, and execution history support.
- Added generic decision outcomes: `EXECUTE`, `SKIP`, `RETRY`, `DELAY`, and `REJECT`.
- Added scheduler support for manual, one-time, daily, weekly, monthly, simple cron, delayed, recurring, and timezone-aware schedules.
- Registered workflow services in `IrisCore` and exposed them through `PluginContext`.
- Added workflow, scheduler, and execution history dashboard pages.
- Integrated Research Agent handoff with the generic decision engine while preserving indirect task-queue/event-bus routing.
- Added Sprint 5 tests for workflow execution, scheduler persistence, decisions, pause/resume, retry, cancellation, service registration, and restart persistence.
