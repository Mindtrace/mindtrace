from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Configuration for MCPLangGraphAgent/LLM provider.

    Attributes:
        model: Model name for the default Ollama provider.
        base_url: Ollama base URL.
        tool_choice: Tool selection policy passed to the LLM (e.g., "any").
        system_prompt: System prompt prefix appended by the default llm node.
        request_timeout: Timeout used by clients where applicable.

    Example:
        AgentConfig(model="qwen2.5:7b", base_url="http://localhost:11434")
    """

    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434"
    tool_choice: str = "any"
    system_prompt: str = "You have access to tools. Use them as needed."
    request_timeout: int = 60
