from dataclasses import dataclass
from fastmcp import Client
from typing import Any

from ..base import AgentConfig as BaseAgentConfig

@dataclass
class LangraphAgentConfig(BaseAgentConfig):
    """Generic configuration for MCP-enabled, tool-augmented agents.

    Attributes:
        tool_choice: Tool selection policy passed to the LLM (e.g., "any").
        mcp_url: Base service URL to connect to MCP ("http://host:port"). The
                 mcp mount path is appended automatically from Service Config.
        mcp_client: Optional existing MCP client instance to use directly. If
                    provided, takes precedence over mcp_url.
    """

    tool_choice: str = "any"
    mcp_url: str | None = None
    mcp_client: Client | None = None
    checkpointer: Any | None = None


@dataclass
class OllamaAgentConfig(LangraphAgentConfig):
    """Configuration for Ollama-backed LLM provider.

    Attributes:
        model: Model name for the default Ollama provider.
        base_url: Ollama base URL.
        system_prompt: Optional system prompt prefix used by the LLM node.

    Example:
        OllamaAgentConfig(model="qwen2.5:7b", base_url="http://localhost:11434", mcp_url="http://localhost:8000")
        # or
        # OllamaAgentConfig(mcp_client=Client("http://localhost:8000/mcp-server/mcp"))
    """

    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434"
    system_prompt: str | None = "You have access to tools. Use them as needed."


