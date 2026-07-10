# IRIS

IRIS is a production-oriented AI orchestration platform built incrementally with Clean Architecture principles. Sprint 2.5 extends the existing Sprint 1 and Sprint 2 foundation with core system services only. It does not add AI integrations or domain workflows.

## Run

```powershell
python main.py
```

If `python` is not on PATH, activate or repair the project virtual environment first.

## Architecture

The application is organized around a small core, service layer, agent layer, and PySide6 dashboard. `IrisCore` remains the composition root and retrieves infrastructure through `ServiceRegistry`. The dashboard uses a view model so UI code displays state without owning business or infrastructure logic.

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

## Dashboard

The dashboard includes an `Overview` page and a `System Services` page. The services page displays:

- Configuration
- Storage
- Secrets
- Process Manager
- Notifications
- Service Registry

Each row shows status, health, and version.

## Tests

```powershell
python -m unittest discover tests
```
