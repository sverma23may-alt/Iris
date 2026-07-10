"""Agent registry for IRIS."""

from __future__ import annotations

from iris.agents.base_agent import BaseAgent


class AgentManager:
    """Manage registered IRIS agents."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent by its unique name."""
        if agent.name in self._agents:
            raise ValueError(f"Agent already registered: {agent.name}")

        self._agents[agent.name] = agent

    def unregister(self, name: str) -> None:
        """Remove an agent by name."""
        if name not in self._agents:
            raise KeyError(f"Agent not registered: {name}")

        del self._agents[name]

    def get_agent(self, name: str) -> BaseAgent | None:
        """Return a registered agent by name, if present."""
        return self._agents.get(name)

    def list_agents(self) -> list[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents.values())
