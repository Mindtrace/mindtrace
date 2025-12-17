from abc import abstractmethod
from typing import Any, ClassVar, List, Optional

import click

from mindtrace.agents.composer.composer import get_agent
from mindtrace.agents.composer.config import (
    BaseAgentWorkflowConfig,
    SettingsLike,
)
from mindtrace.agents.providers.llm.strands import (
    get_model_from_provider,
    resolve_provider_config,
)
from mindtrace.core import MindtraceABC
from mindtrace.registry import Registry


class AgentRegistry:
    _registry: ClassVar[Optional[Registry]] = None
    _registry_dir: ClassVar[str] = "~/.cache/mindtrace/agents/registry"

    @classmethod
    def _get_registry(cls) -> Registry:
        """Get or create the Registry instance."""
        if cls._registry is None:
            cls._registry = Registry(registry_dir=cls._registry_dir, version_objects=True)
        return cls._registry

    @classmethod
    def register(cls, name: str, description: str, cli_module: str, cli_class: str, version: Optional[str] = None):
        """Register an agent type with its metadata.

        Stores agent metadata in Registry for persistence.
        With versioning enabled, each registration creates a new version.

        Args:
            name: Name of the agent type.
            description: Description of the agent.
            cli_module: Module path where CLI class is located.
            cli_class: Name of the CLI class.
            version: Optional version string. If None, auto-increments.
        """
        agent_info = {
            "name": name,
            "description": description,
            "cli_module": cli_module,
            "cli_class": cli_class,
        }

        registry = cls._get_registry()

        # If version is specified, check if it already exists
        if version is not None:
            if registry.has_object(name=f"agent:type:{name}", version=version):
                # Agent already exists at this version, skip registration (idempotent)
                registry.logger.debug(f"Agent {name} version {version} already exists, skipping registration.")
                return

        try:
            registry.save(f"agent:type:{name}", agent_info, version=version)
        except ValueError as e:
            # Handle case where version already exists (race condition)
            if "already exists" in str(e):
                registry.logger.debug(f"Agent {name} version {version} already exists, skipping registration.")
            else:
                raise

    @classmethod
    def get(cls, name: str, version: Optional[str] = "latest") -> dict | None:
        """Get agent metadata by name.

        Loads from Registry. With versioning enabled, can load specific versions.

        Args:
            name: Name of the agent type.
            version: Version to load. Defaults to "latest".

        Returns:
            Agent metadata dict, or None if not found.
        """
        registry = cls._get_registry()
        try:
            return registry.load(f"agent:type:{name}", version=version)
        except ValueError:
            return None

    @classmethod
    def list_versions(cls, name: str) -> list[str]:
        """List all versions of an agent type.

        Args:
            name: Name of the agent type.

        Returns:
            List of version strings.
        """
        registry = cls._get_registry()
        try:
            return registry.list_versions(f"agent:type:{name}")
        except ValueError:
            return []

    @classmethod
    def all(cls) -> dict[str, dict]:
        """Get all registered agent metadata.

        Loads all agents from Registry.
        """
        registry = cls._get_registry()
        all_objects = registry.list_objects()

        agents = {}
        for obj_name in all_objects:
            if obj_name.startswith("agent:type:"):
                agent_name = obj_name.replace("agent:type:", "", 1)
                agent_info = cls.get(agent_name)
                if agent_info:
                    agents[agent_name] = agent_info

        return agents

    @classmethod
    def names(cls) -> list[str]:
        """Get list of all registered agent names."""
        return list(cls.all().keys())

    @classmethod
    def delete(cls, name: str):
        """Delete an agent type from the registry."""
        registry = cls._get_registry()
        try:
            registry.delete(f"agent:type:{name}")
        except ValueError:
            pass


class BaseAgent(MindtraceABC):
    agent_name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def __init__(self, config_override: SettingsLike = None, **kwargs):
        super().__init__(**kwargs)
        self.config = BaseAgentWorkflowConfig(config_override)

    def _get_agent_config(self) -> dict:
        agents = self.config.get("MT_AGENTS", {})
        if self.agent_name not in agents:
            raise KeyError(f"Agent '{self.agent_name}' not found in MT_AGENTS. Available agents: {list(agents.keys())}")

        agent_data = agents[self.agent_name]

        return agent_data

    def _get_model_config(self, model_key: str) -> dict:
        agent_config = self._get_agent_config()

        models = agent_config.get("models", {})

        if model_key not in models:
            raise KeyError(
                f"Model '{model_key}' not found in agent '{self.agent_name}' models. "
                f"Available models: {list(models.keys())}"
            )

        model_data = models[model_key]

        return model_data

    def get_model(self, model_key: str, **kwargs) -> Any:
        model_config = self._get_model_config(model_key)

        providers = self.config.get("MT_LLM_PROVIDERS", {})

        provider_config = resolve_provider_config(provider_key=model_config["provider"], providers=providers)

        model_kwargs = {**kwargs}

        return get_model_from_provider(
            provider_config=provider_config, model_name=model_config["model_name"], **model_kwargs
        )

    def get_agent(self, model_key: str, tools: Optional[List] = None, **kwargs) -> Any:
        model_config = self._get_model_config(model_key)
        model = self.get_model(model_key)

        return get_agent(model=model, system_prompt=model_config["system_prompt"], tools=tools or [], **kwargs)

    @abstractmethod
    async def run(self, input: str, **kwargs) -> dict:
        pass


class BaseAgentCLI:
    agent_class: ClassVar[type[BaseAgent]] = None

    @classmethod
    @abstractmethod
    def cli_group(cls) -> click.Group:
        pass
