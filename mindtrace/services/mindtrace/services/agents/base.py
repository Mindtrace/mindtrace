from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterable, Dict, List, Optional

from mindtrace.core import MindtraceABC


@dataclass
class AgentConfig:
    """Configuration parameters for a MindtraceAgent.

    Attributes:
        model (Optional[str]): Identifier of the model to use (e.g., "gpt-4").
        endpoint (Optional[str]): API endpoint or server URL for the agent (e.g., OpenAI, ADK).
        agent_card (Dict[str, Any]): Free-form metadata about the agent (e.g., name, version).
        skills (List[str]): List of skill identifiers or abilities this agent has access to.
        system_prompt (Optional[str]): Optional system-level prompt or instructions for initialization.
    """
    model: Optional[str] = None
    endpoint: Optional[str] = None  # e.g., OpenAI/ADK server, etc.
    agent_card: Optional[Dict[str, Any]] = field(default_factory=dict)
    skills: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None


class MindtraceAgent(MindtraceABC):
    """Base interface for all Mindtrace agent adapters.

    Subclasses must implement the `astream` method to provide streaming behavior
    for agent responses, yielding structured event dictionaries.

    Example usage:

        class MyAgent(MindtraceAgent):
            async def astream(self, messages, *, context=None):
                for part in some_llm_stream(messages):
                    yield {"event": "message", "data": {"text": part}}

                yield {"event": "final", "data": {"status": "done"}}
    """

    def __init__(self, agent_config: AgentConfig):
        """Initialize the agent with the given configuration.

        Args:
            agent_config (AgentConfig): Configuration settings for the agent.
        """
        self.agent_config = agent_config

    async def astream(
        self,
        messages: List[Dict[str, Any]],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterable[Dict[str, Any]]:
        """Asynchronously stream agent events based on the provided input messages.

        Adapters must override this method to drive framework-specific logic, such as
        calling LangGraph `.astream()`, OpenAI's streaming endpoints, or ADK sessions.

        Args:
            messages (List[Dict[str, Any]]): A sequence of message dictionaries representing
                the full conversation history, new user input, and any tool call metadata.
            context (Optional[Dict[str, Any]]): Optional execution context, such
                as request-scoped metadata, session identifiers, or provenance tracking.

        Yields:
            AsyncIterable[Dict[str, Any]]: A sequence of event dictionaries with the shape:
              {
                "event": str,       # e.g., "message", "status", "tool_call", "final", "error"
                "data": Any         # Usually a dict or primitive with event payload
              }

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError
