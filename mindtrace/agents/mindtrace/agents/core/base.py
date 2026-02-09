"""Concrete implementation of the mindtrace agent following Pydantic AI's tool execution pattern.

This module provides the complete agent implementation with tool execution flow:
1. ToolManager - validates args and orchestrates execution
2. Toolset - handles actual tool execution
3. FunctionSchema - handles RunContext injection

Reference: `mindtrace_starter/TOOL_EXECUTION_FLOW.md`
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from ..models import Model, ModelRequestParameters, ModelResponse
from ..prompts import UserContent, UserPromptPart
from ..tools import RunContext, Tool
from .._run_context import AgentDepsT as _AgentDepsT
from .._tool_manager import ToolManager
from ..toolsets.function import FunctionToolset
from .abstract import AbstractMindtraceAgent, OutputDataT


# Re-export for convenience
AgentDepsT = _AgentDepsT


@dataclass
class MindtraceAgent(AbstractMindtraceAgent[AgentDepsT, OutputDataT]):
    """Complete agent implementation following Pydantic AI's architecture.
    
    This agent follows the complete tool execution flow from Pydantic AI:
    
    Flow:
    ```
    ModelResponse (with tool_calls)
    → MindtraceAgent.run()
    → tool_manager.handle_call()
    → tool_manager._call_tool() (validate args)
    → toolset.call_tool()
    → tool.call_func(tool_args, ctx)
    → FunctionSchema.call() (handles RunContext injection)
    → actual function execution
    ```
    
    Reference: `mindtrace_starter/TOOL_EXECUTION_FLOW.md`
    
    Example:
        ```python
        from mindtrace_starter.models.openai_chat import OpenAIChatModel
        from mindtrace_starter.providers import OllamaProvider
        from mindtrace_starter.agent import MindtraceAgent
        from mindtrace_starter.tools import Tool, RunContext
        
        # Define a tool
        def get_weather(ctx: RunContext[None], city: str) -> str:
            return f"Weather in {city}: Sunny, 72°F"
        
        weather_tool = Tool(get_weather)
        
        # Create model
        provider = OllamaProvider(base_url='http://localhost:11434/v1')
        model = OpenAIChatModel('llama3', provider=provider)
        
        # Create agent
        agent = MindtraceAgent(
            model=model,
            tools=[weather_tool],
            name='weather_agent'
        )
        
        # Run agent
        result = await agent.run("What's the weather in Paris?")
        ```
    """
    
    model: Model = field(repr=False)
    """The model to use for generating responses."""
    
    tools: Sequence[Tool[AgentDepsT]] = field(default_factory=list)
    """List of tools available to the agent."""
    
    _name: str | None = None
    _deps_type: type = field(default_factory=lambda: type(None))
    _output_type: type[OutputDataT] = field(default=str)  # type: ignore
    
    # Internal state
    _entered_count: int = field(default=0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _tool_manager: ToolManager[AgentDepsT] | None = field(default=None, init=False, repr=False)
    
    def __post_init__(self):
        """Initialize the tool manager after dataclass initialization."""
        # Create FunctionToolset and add tools
        # Reference: `pydantic_ai_slim/pydantic_ai/toolsets/function.py:37-383`
        toolset = FunctionToolset[AgentDepsT]()
        for tool in self.tools:
            toolset.add_tool(tool)
        
        # Create ToolManager with the toolset
        # Reference: `pydantic_ai_slim/pydantic_ai/_tool_manager.py:30-212`
        self._tool_manager = ToolManager(toolset=toolset)
    
    @property
    def name(self) -> str | None:
        """The name of the agent."""
        return self._name
    
    @name.setter
    def name(self, value: str | None) -> None:
        """Set the name of the agent."""
        self._name = value
    
    @property
    def deps_type(self) -> type:
        """The type of dependencies used by the agent."""
        return self._deps_type
    
    @property
    def output_type(self) -> type[OutputDataT]:
        """The type of data output by agent runs."""
        return self._output_type
    
    async def run(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> OutputDataT:
        """Run the agent with a user prompt.
        
        This implements the complete tool execution flow from Pydantic AI:
        
        1. Send user message to model
        2. If model returns tool calls:
           a. Prepare ToolManager for run step
           b. For each tool call:
              - tool_manager.handle_call() validates args
              - tool_manager._call_tool() parses args
              - toolset.call_tool() executes
              - FunctionSchema.call() handles RunContext injection
           c. Send tool results back to model
        3. Repeat until model returns final answer
        
        Reference: `mindtrace_starter/TOOL_EXECUTION_FLOW.md`
        
        Args:
            input_data: The user's input (user_prompt): a string, or a sequence of text
                and images (e.g. `["What's in this image?", BinaryContent.from_path(Path("photo.png"))]`).
            deps: Optional dependencies to inject into tools
            **kwargs: Additional arguments
        
        Returns:
            The final result from the model
        """
        if input_data is None:
            input_data = ''
        # Pass UserPromptPart to model; model's _map_user_prompt converts to API format (Pydantic AI pattern)
        messages = [{'role': 'user', 'content': UserPromptPart(content=input_data)}]
        
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Get tool definitions from toolset
            # Reference: `pydantic_ai_slim/pydantic_ai/_agent_graph.py:392-433`
            ctx = RunContext(deps=deps)
            if self._tool_manager:
                await self._tool_manager.for_run_step(ctx)
                tool_definitions = [
                    tool.tool_def
                    for tool in (self._tool_manager.tools or {}).values()
                ]
            else:
                tool_definitions = []
            
            # Make request to model
            request_params = ModelRequestParameters(
                function_tools=tool_definitions if tool_definitions else []
            )
            
            response: ModelResponse = await self.model.request(
                messages=messages,
                model_settings=kwargs.get('model_settings'),
                model_request_parameters=request_params,
            )
            
            # Add model response to message history
            messages.append({
                'role': 'assistant',
                'content': response.text,
            })
            
            # If model returned tool calls, execute them
            # This follows the complete flow:
            # _handle_tool_calls → process_tool_calls → _call_tools → _call_tool
            # Reference: `mindtrace_starter/TOOL_EXECUTION_FLOW.md:7-112`
            if response.tool_calls and self._tool_manager:
                # Execute each tool call following Pydantic AI's pattern
                # Reference: `pydantic_ai_slim/pydantic_ai/_agent_graph.py:1196-1280`
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call.get('arguments', '{}')
                    
                    try:
                        # Execute tool via ToolManager
                        # This follows the flow:
                        # tool_manager.handle_call()
                        # → tool_manager._call_tool() (validates args)
                        # → toolset.call_tool()
                        # → tool.call_func(tool_args, ctx)
                        # → FunctionSchema.call() (handles RunContext injection)
                        # Reference: `mindtrace_starter/TOOL_EXECUTION_FLOW.md:114-217`
                        tool_result = await self._tool_manager.handle_call(
                            tool_name=tool_name,
                            tool_args_json=tool_args,
                        )
                        
                        # Add tool result to messages
                        # Reference: `pydantic_ai_slim/pydantic_ai/_agent_graph.py:1254-1262`
                        messages.append({
                            'role': 'tool',
                            'tool_call_id': tool_call.get('id'),
                            'name': tool_name,
                            'content': str(tool_result),
                        })
                    except Exception as e:
                        # Handle tool execution errors
                        messages.append({
                            'role': 'tool',
                            'tool_call_id': tool_call.get('id'),
                            'name': tool_name,
                            'content': f'Error: {str(e)}',
                        })
                
                # Continue loop to send tool results back to model
                continue
            else:
                # No tool calls - we have the final answer
                return response.text  # type: ignore
        
        # If we hit max iterations, return the last response
        return response.text  # type: ignore
    
    @asynccontextmanager
    async def iter(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Iterate over agent execution steps.
        
        This is a simplified version that yields steps during execution.
        
        Args:
            input_data: The user's input (string or sequence of text and images).
            deps: Optional dependencies
            **kwargs: Additional arguments
        
        Yields:
            Execution steps
        """
        # For minimal version, just yield the final result
        # In a full implementation, you'd yield intermediate steps
        result = await self.run(input_data, deps=deps, **kwargs)
        yield {'step': 'complete', 'result': result}
    
    async def __aenter__(self) -> MindtraceAgent[AgentDepsT, OutputDataT]:
        """Enter the agent context."""
        async with self._lock:
            if self._entered_count == 0:
                # Initialize resources if needed
                pass
            self._entered_count += 1
        return self
    
    async def __aexit__(self, *args: Any) -> bool | None:
        """Exit the agent context and clean up."""
        async with self._lock:
            self._entered_count -= 1
            if self._entered_count == 0:
                # Clean up resources if needed
                pass
        return None


__all__ = [
    'MindtraceAgent',
    'AgentDepsT',
]
