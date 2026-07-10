"""Status values used across IRIS."""

from __future__ import annotations

from enum import Enum


class ServiceStatus(str, Enum):
    """Lifecycle status for platform services."""

    ONLINE = "Online"
    OFFLINE = "Offline"


class AgentStatus(str, Enum):
    """Lifecycle status for agents."""

    CREATED = "Created"
    INITIALIZED = "Initialized"
    RUNNING = "Running"
    STOPPED = "Stopped"
    ERROR = "Error"
