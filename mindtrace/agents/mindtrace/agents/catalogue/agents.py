from abc import abstractmethod
from typing import ClassVar, Any, Optional, List

import click

from mindtrace.core import MindtraceABC
from mindtrace.agents.composer.config import (
    BaseAgentWorkflowConfig,
    SettingsLike,
)
from mindtrace.agents.providers.llm.strands import (
    get_model_from_provider,
    resolve_provider_config,
)
from mindtrace.agents.composer.composer import get_agent


class AgentRegistry:
    _agents: ClassVar[dict[str, dict]] = {}

    @classmethod
    def register(cls, name: str, description: str, cli_module: str, cli_class: str):
        cls._agents[name] = {
            "name": name,
            "description": description,
            "cli_module": cli_module,
            "cli_class": cli_class,
        }

    @classmethod
    def get(cls, name: str) -> dict | None:
        return cls._agents.get(name)

    @classmethod
    def get_cli_class(cls, name: str):
        info = cls._agents.get(name)
        if not info:
            return None
        import importlib
        module = importlib.import_module(info["cli_module"])
        return getattr(module, info["cli_class"])

    @classmethod
    def all(cls) -> dict[str, dict]:
        return cls._agents.copy()

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._agents.keys())

    @classmethod
    def register_all_commands(cls, parent_group: click.Group):
        for name in cls._agents:
            cli_class = cls.get_cli_class(name)
            if cli_class:
                parent_group.add_command(cli_class.cli_group(), name=name)


class BaseAgent(MindtraceABC):
    agent_name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def __init__(self, config_override: SettingsLike = None, **kwargs):
        super().__init__(**kwargs)
        self.config = BaseAgentWorkflowConfig(config_override)

    def _get_agent_config(self) -> dict:
        agents = self.config.get("MT_AGENTS", {})
        if self.agent_name not in agents:
            raise KeyError(
                f"Agent '{self.agent_name}' not found in MT_AGENTS. "
                f"Available agents: {list(agents.keys())}"
            )
        
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
        
        provider_config = resolve_provider_config(
            provider_key=model_config["provider"],
            providers=providers
        )
        
        model_kwargs = {
            **kwargs
        }
        

        return get_model_from_provider(
            provider_config=provider_config,
            model_name=model_config["model_name"],
            **model_kwargs
        )

    def get_agent(self, model_key: str, tools: Optional[List] = None, **kwargs) -> Any:
        model_config = self._get_model_config(model_key)
        model = self.get_model(model_key)
        
        return get_agent(
            model=model,
            system_prompt=model_config["system_prompt"],
            tools=tools or [],
            **kwargs
        )

    @abstractmethod
    async def run(self, input: str, **kwargs) -> dict:
        pass


class BaseAgentCLI:
    agent_class: ClassVar[type[BaseAgent]] = None

    @classmethod
    @abstractmethod
    def cli_group(cls) -> click.Group:
        pass
