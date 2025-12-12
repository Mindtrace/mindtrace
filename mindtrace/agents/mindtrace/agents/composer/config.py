from typing import Optional, Dict, List , Literal

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings

from mindtrace.core.config import CoreConfig, SettingsLike



class AgentPathsModel(BaseModel):
    MEMORY_DIR: str = "~/.cache/mindtrace/agents/memory"
    CONFIG_FILE: str = "~/.config/mindtrace/agents/base/config.json"

class LLMProviderBase(BaseModel):
    type: str


class OpenAIProvider(LLMProviderBase):
    type: Literal["openai"] = "openai"
    api_key: Optional[str] = None
    default_model: Optional[str] = None


class OllamaProvider(LLMProviderBase):
    type: Literal["ollama"] = "ollama"
    base_url: str
    default_model: Optional[str] = None

LLMProviderConfig = OpenAIProvider | OllamaProvider

class PathsConfig(BaseModel):
    memory_dir: str = "~/.cache/mindtrace/agents/memory"
    config_dir: str = "~/.cache/mindtrace/agents/workflows"


class AgentModelConfig(BaseModel):
    provider: str                 # key into workflow.providers
    model_name: str
    system_prompt: str
    supports_function_calling: bool = True


class AgentConfig(BaseModel):
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    models: Dict[str, AgentModelConfig]          # e.g. primary, summarizer, logql_generator
 

class BaseAgentSettings(BaseSettings):
    MT_LLM_PROVIDERS: Dict[str, LLMProviderConfig] = {
        "ollama": OllamaProvider(
            type="ollama",
            base_url="http://localhost:11434",
            default_model="llama3"
        ),
        "openai": OpenAIProvider(
            type="openai",
            api_key="XX",
            default_model="gpt-4o-mini"
        )
    }
    MT_AGENT_PATHS: PathsConfig = PathsConfig()
    MT_AGENTS: Dict[str, AgentConfig] = {}

    model_config = {"env_nested_delimiter": "__"}


class BaseAgentWorkflowConfig(CoreConfig):
    def __init__(self, extra_settings: SettingsLike = None, *, apply_env_overrides: bool = False):
        if extra_settings is None:
            extras = [BaseAgentSettings()]
        elif isinstance(extra_settings, list):
            extras = [BaseAgentSettings()] + extra_settings
        else:
            extras = [BaseAgentSettings(), extra_settings]
        super().__init__(extra_settings=extras, apply_env_overrides=apply_env_overrides)
