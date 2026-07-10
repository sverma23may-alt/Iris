"""Plugin discovery for IRIS agents."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType

from iris.agents.base_agent import BaseAgent
from iris.services.event_bus import EventBus
from iris.services.logger import get_logger
from iris.plugins.context import PluginContext


class PluginLoader:
    """Discover and instantiate agent plugins from a directory."""

    def __init__(
        self,
        plugins_path: Path | None = None,
        event_bus: EventBus | None = None,
        context: PluginContext | None = None,
    ) -> None:
        self._logger = get_logger(__name__)
        self._plugins_path = plugins_path or Path(__file__).resolve().parents[1] / "plugins"
        self._event_bus = event_bus
        self._context = context

    def discover(self) -> list[BaseAgent]:
        """Discover plugins that inherit from BaseAgent."""
        self._plugins_path.mkdir(parents=True, exist_ok=True)
        agents: list[BaseAgent] = []

        for plugin_file in self._plugins_path.glob("*.py"):
            if plugin_file.name == "__init__.py":
                continue

            module = self._load_module(plugin_file)
            agents.extend(self._agents_from_module(module))

        self._logger.info("Discovered {} plugin agents", len(agents))
        return agents

    def _load_module(self, plugin_file: Path) -> ModuleType:
        module_name = f"iris.plugins.{plugin_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin: {plugin_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _agents_from_module(self, module: ModuleType) -> list[BaseAgent]:
        agents: list[BaseAgent] = []
        for value in module.__dict__.values():
            if not isinstance(value, type):
                continue
            if value is BaseAgent or not issubclass(value, BaseAgent):
                continue

            agent = self._create_agent(value)
            if self._event_bus is not None:
                agent.attach_event_bus(self._event_bus)
            agents.append(agent)
        return agents

    def _create_agent(self, agent_type: type[BaseAgent]) -> BaseAgent:
        """Instantiate legacy or context-aware plugin agents."""
        if self._context is not None and self._accepts_plugin_context(agent_type):
            return agent_type(self._context)

        return agent_type()

    def _accepts_plugin_context(self, agent_type: type[BaseAgent]) -> bool:
        signature = inspect.signature(agent_type)
        parameters = list(signature.parameters.values())
        if not parameters:
            return False

        parameter = parameters[0]
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return False

        annotation = parameter.annotation
        return annotation is PluginContext or parameter.name == "context"
