"""Concrete implementation of the mindtrace agent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from ..events import (
    AgentRunResult,
    AgentRunResultEvent,
    NativeEvent,
    PartEndEvent,
    ToolResultEvent,
)
from ..messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart
from ..messages._parts import SystemPromptPart
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
    """Concrete implementation of the mindtrace agent.
    
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

    system_prompt: str | None = None
    """Optional system prompt prepended as a system message on every run."""

    _name: str | None = None
    _deps_type: type = field(default_factory=lambda: type(None))
    _output_type: type[OutputDataT] = field(default=str)  # type: ignore
    
    # Internal state
    _entered_count: int = field(default=0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _tool_manager: ToolManager[AgentDepsT] | None = field(default=None, init=False, repr=False)
    
    def __post_init__(self):
        """Initialize the tool manager after dataclass initialization."""
        toolset = FunctionToolset[AgentDepsT]()
        for tool in self.tools:
            toolset.add_tool(tool)
        self._tool_manager = ToolManager(toolset=toolset)

    def _build_messages(
        self,
        input_data: str | Sequence[UserContent],
        message_history: list[ModelMessage] | None,
    ) -> list[ModelMessage]:
        """Build the initial message list for a run.

        Order:
          1. System message (if system_prompt is set) — always first, not stored
             in history so it is not duplicated across turns.
          2. Prior conversation history (if provided).
          3. The new user message.
        """
        messages: list[ModelMessage] = []

        if self.system_prompt:
            messages.append(
                ModelMessage(
                    role="system",
                    parts=[SystemPromptPart(content=self.system_prompt)],
                )
            )

        if message_history:
            messages.extend(message_history)

        messages.append(
            ModelMessage(role="user", parts=[UserPromptPart(content=input_data)])
        )
        return messages
    
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
        message_history: list[ModelMessage] | None = None,
        **kwargs: Any,
    ) -> OutputDataT:
        """Run the agent with a user prompt.

        This implements the complete tool execution flow:

        1. Send user message to model (preceded by system prompt + history if set)
        2. If model returns tool calls:
           a. Prepare ToolManager for run step
           b. For each tool call:
              - tool_manager.handle_call() validates args
              - toolset.call_tool() executes with RunContext injection
           c. Send tool results back to model
        3. Repeat until model returns final answer

        Args:
            input_data: The user's input: a string or sequence of text/images.
            deps: Optional dependencies to inject into tools.
            message_history: Optional mutable list of prior ModelMessage objects.
                             New messages from this run are appended in-place so
                             the caller can maintain multi-turn conversation state.
            **kwargs: Additional arguments.

        Returns:
            The final text result from the model.
        """
        if input_data is None:
            input_data = ''
        messages = self._build_messages(input_data, message_history)
        # Track where new messages start so we can append them to history later
        history_start = len(messages) - 1  # include the new user message in history
        
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Get tool definitions from toolset
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
            
            # Append assistant message: text and optional tool calls
            assistant_parts: list[TextPart | ToolCallPart] = []
            if response.text:
                assistant_parts.append(TextPart(content=response.text))
            for tool_call in response.tool_calls or []:
                assistant_parts.append(
                    ToolCallPart(
                        tool_call_id=tool_call.get('id', ''),
                        tool_name=tool_call['name'],
                        args=tool_call.get('arguments', '{}'),
                    )
                )
            if not assistant_parts:
                assistant_parts.append(TextPart(content=''))
            messages.append(ModelMessage(role='assistant', parts=assistant_parts))
            
            if response.tool_calls and self._tool_manager:
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call.get('arguments', '{}')
                    try:
                        tool_result = await self._tool_manager.handle_call(
                            tool_name=tool_name,
                            tool_args_json=tool_args,
                        )
                        content = str(tool_result)
                    except Exception as e:
                        content = f'Error: {str(e)}'
                    messages.append(
                        ModelMessage(
                            role='tool',
                            parts=[
                                ToolReturnPart(
                                    tool_call_id=tool_call.get('id', ''),
                                    content=content,
                                )
                            ],
                        )
                    )
                continue
            else:
                # No tool calls — final answer reached
                # Append new messages (excluding system prompt) to history
                if message_history is not None:
                    message_history.extend(messages[history_start:])
                return response.text  # type: ignore

        # Hit max iterations — still persist history
        if message_history is not None:
            message_history.extend(messages[history_start:])
        return response.text  # type: ignore

    async def run_stream_events(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        message_history: list[ModelMessage] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[NativeEvent]:
        """Run the agent and stream events.

        Yields PartStartEvent, PartDeltaEvent, PartEndEvent from the model,
        ToolResultEvent for each tool result, and AgentRunResultEvent with the
        final result at the end.

        Args:
            input_data: User input (string or sequence of text/images).
            deps: Optional dependencies for tools.
            message_history: Optional mutable list for multi-turn history.
                             New messages are appended in-place.
            **kwargs: Passed to model (e.g. model_settings).

        Yields:
            NativeEvent (part lifecycle, tool results, run result).
        """
        if input_data is None:
            input_data = ''
        messages = self._build_messages(input_data, message_history)
        history_start = len(messages) - 1  # include the new user message in history
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            ctx = RunContext(deps=deps)
            if self._tool_manager:
                await self._tool_manager.for_run_step(ctx)
                tool_definitions = [
                    tool.tool_def
                    for tool in (self._tool_manager.tools or {}).values()
                ]
            else:
                tool_definitions = []
            request_params = ModelRequestParameters(
                function_tools=tool_definitions if tool_definitions else []
            )

            parts_by_index: dict[int, TextPart | ToolCallPart] = {}
            async for event in self.model.request_stream(
                messages=messages,
                model_settings=kwargs.get('model_settings'),
                model_request_parameters=request_params,
            ):
                yield event
                if isinstance(event, PartEndEvent) and event.part is not None:
                    if isinstance(event.part, (TextPart, ToolCallPart)):
                        parts_by_index[event.index] = event.part

            assistant_parts: list[TextPart | ToolCallPart] = [
                parts_by_index[i]
                for i in sorted(parts_by_index)
                if parts_by_index[i] is not None
            ]
            if not assistant_parts:
                assistant_parts.append(TextPart(content=''))
            messages.append(ModelMessage(role='assistant', parts=assistant_parts))

            tool_calls = [p for p in assistant_parts if isinstance(p, ToolCallPart)]
            if not tool_calls or not self._tool_manager:
                text = ''.join(
                    p.content for p in assistant_parts if isinstance(p, TextPart)
                )
                if message_history is not None:
                    message_history.extend(messages[history_start:])
                yield AgentRunResultEvent(
                    result=AgentRunResult(output=text or ''),
                )
                return

            for tool_call in tool_calls:
                try:
                    tool_result = await self._tool_manager.handle_call(
                        tool_name=tool_call.tool_name,
                        tool_args_json=tool_call.args,
                    )
                    content = str(tool_result)
                except Exception as e:
                    content = f'Error: {str(e)}'
                yield ToolResultEvent(
                    tool_call_id=tool_call.tool_call_id,
                    content=content,
                )
                messages.append(
                    ModelMessage(
                        role='tool',
                        parts=[
                            ToolReturnPart(
                                tool_call_id=tool_call.tool_call_id,
                                content=content,
                            )
                        ],
                    )
                )

        # Max iterations — still persist history
        if message_history is not None:
            message_history.extend(messages[history_start:])
        last_parts = messages[-1].parts if messages else []
        text = ''.join(
            p.content for p in last_parts if isinstance(p, TextPart)
        )
        yield AgentRunResultEvent(result=AgentRunResult(output=text or ''))

    @asynccontextmanager
    async def iter(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        message_history: list[ModelMessage] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Iterate over agent execution steps one at a time.

        Yields one dict per step so callers can observe intermediate state:

        - ``{'step': 'model_response', 'iteration': int, 'text': str, 'tool_calls': list}``
          — emitted after each LLM response.
        - ``{'step': 'tool_result', 'tool_name': str, 'tool_call_id': str, 'result': str}``
          — emitted after each tool execution (one per tool call).
        - ``{'step': 'complete', 'result': str}``
          — emitted once when the agent reaches a final answer or hits the
          iteration limit.

        Usage::

            async with agent.iter("What's the weather?") as steps:
                async for step in steps:
                    print(step)

        Args:
            input_data: The user's input.
            deps: Optional dependencies to inject into tools.
            **kwargs: Additional arguments (e.g. model_settings).
        """
        async def _run_steps() -> AsyncIterator[dict[str, Any]]:
            _input: str | Sequence[UserContent] = input_data if input_data is not None else ''
            messages = self._build_messages(_input, message_history)
            history_start = len(messages) - 1  # include the new user message in history

            max_iterations = 10
            last_text = ''

            for iteration in range(max_iterations):
                ctx = RunContext(deps=deps, step=iteration)
                if self._tool_manager:
                    await self._tool_manager.for_run_step(ctx)
                    tool_definitions = [
                        tool.tool_def
                        for tool in (self._tool_manager.tools or {}).values()
                    ]
                else:
                    tool_definitions = []

                request_params = ModelRequestParameters(
                    function_tools=tool_definitions if tool_definitions else []
                )

                response: ModelResponse = await self.model.request(
                    messages=messages,
                    model_settings=kwargs.get('model_settings'),
                    model_request_parameters=request_params,
                )
                last_text = response.text or ''

                yield {
                    'step': 'model_response',
                    'iteration': iteration,
                    'text': last_text,
                    'tool_calls': response.tool_calls or [],
                }

                # Build and append assistant message
                assistant_parts: list[TextPart | ToolCallPart] = []
                if response.text:
                    assistant_parts.append(TextPart(content=response.text))
                for tc in response.tool_calls or []:
                    assistant_parts.append(
                        ToolCallPart(
                            tool_call_id=tc.get('id', ''),
                            tool_name=tc['name'],
                            args=tc.get('arguments', '{}'),
                        )
                    )
                if not assistant_parts:
                    assistant_parts.append(TextPart(content=''))
                messages.append(ModelMessage(role='assistant', parts=assistant_parts))

                if response.tool_calls and self._tool_manager:
                    for tc in response.tool_calls:
                        try:
                            tool_result = await self._tool_manager.handle_call(
                                tool_name=tc['name'],
                                tool_args_json=tc.get('arguments', '{}'),
                            )
                            content = str(tool_result)
                        except Exception as exc:
                            content = f'Error: {exc}'

                        yield {
                            'step': 'tool_result',
                            'tool_name': tc['name'],
                            'tool_call_id': tc.get('id', ''),
                            'result': content,
                        }

                        messages.append(
                            ModelMessage(
                                role='tool',
                                parts=[
                                    ToolReturnPart(
                                        tool_call_id=tc.get('id', ''),
                                        content=content,
                                    )
                                ],
                            )
                        )
                    # Continue loop with tool results fed back
                    continue

                # No tool calls — final answer reached
                if message_history is not None:
                    message_history.extend(messages[history_start:])
                yield {'step': 'complete', 'result': last_text}
                return

            # Hit the iteration limit
            if message_history is not None:
                message_history.extend(messages[history_start:])
            yield {'step': 'complete', 'result': last_text}

        yield _run_steps()
    
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
