from typing import Protocol

from langchain_core.runnables import Runnable
from langchain_ollama.chat_models import ChatOllama

from mindtrace.core import Mindtrace


class LLMProvider(Protocol):
    """Protocol for pluggable LLM providers used by MCPLangGraphAgent.

    Implementors must return a LangChain Runnable that supports `.invoke(messages)`
    and accepts tool bindings via `with_tools`.
    """
    def with_tools(self, tools, tool_choice: str = "any") -> Runnable:
        ...


class OllamaProvider(Mindtrace):
    """Default LLM provider using Ollama via LangChain's ChatOllama.

    Example:
        provider = OllamaProvider(model="qwen2.5:7b", base_url="http://localhost:11434")
        llm = provider.with_tools(tools, tool_choice="any")
        resp = llm.invoke(messages)
    """
    def __init__(self, model: str, base_url: str):
        super().__init__()
        self._llm = ChatOllama(model=model, base_url=base_url)

    def with_tools(self, tools, tool_choice: str = "any") -> Runnable:
        return self._llm.bind_tools(tools, tool_choice=tool_choice)

