from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from .._run_context import AgentDepsT as _AgentDepsT
from .._tool_manager import ToolManager
from ..callbacks import AgentCallbacks, _invoke
from ..events import (
    AgentRunResult,
    AgentRunResultEvent,
    NativeEvent,
    PartEndEvent,
    ToolResultEvent,
)
from ..history import AbstractHistoryStrategy
from ..messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart
from ..messages._parts import SystemPromptPart
from ..models import Model, ModelRequestParameters, ModelResponse
from ..prompts import UserContent, UserPromptPart
from ..tools import RunContext, Tool
from ..toolsets.function import FunctionToolset
from .abstract import AbstractMindtraceAgent, OutputDataT

AgentDepsT = _AgentDepsT


class MindtraceAgent(AbstractMindtraceAgent[AgentDepsT, OutputDataT]):
    def __init__(
        self,
        model: Model,
        *,
        tools: Sequence[Tool] | None = None,
        system_prompt: str | None = None,
        name: str | None = None,
        deps_type: type = type(None),
        output_type: type = str,
        callbacks: AgentCallbacks | None = None,
        history: AbstractHistoryStrategy | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.model = model
        self.tools = list(tools or [])
        self.system_prompt = system_prompt
        self._name = name
        self._deps_type = deps_type
        self._output_type = output_type
        self.callbacks = callbacks
        self.history = history
        self._entered_count = 0
        self._lock = asyncio.Lock()
        toolset: FunctionToolset = FunctionToolset()
        for tool in self.tools:
            toolset.add_tool(tool)
        self._tool_manager: ToolManager = ToolManager(toolset=toolset)

    @property
    def name(self) -> str | None:
        return self._name

    @name.setter
    def name(self, value: str | None) -> None:
        self._name = value

    @property
    def deps_type(self) -> type:
        return self._deps_type

    @property
    def output_type(self) -> type[OutputDataT]:
        return self._output_type  # type: ignore

    def _build_messages(
        self,
        input_data: str | Sequence[UserContent],
        message_history: list[ModelMessage] | None,
    ) -> list[ModelMessage]:
        messages: list[ModelMessage] = []
        if self.system_prompt:
            messages.append(ModelMessage(role="system", parts=[SystemPromptPart(content=self.system_prompt)]))
        if message_history:
            messages.extend(message_history)
        messages.append(ModelMessage(role="user", parts=[UserPromptPart(content=input_data)]))
        return messages

    async def run(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        session_id: str | None = None,
        message_history: list[ModelMessage] | None = None,
        **kwargs: Any,
    ) -> OutputDataT:
        if input_data is None:
            input_data = ""

        loaded_history: list[ModelMessage] | None = None
        if self.history is not None and session_id is not None:
            loaded_history = await self.history.load(session_id)

        effective_history = message_history if message_history is not None else loaded_history
        messages = self._build_messages(input_data, effective_history)
        history_start = len(messages) - 1
        save_from = 1 if self.system_prompt else 0

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            ctx = RunContext(deps=deps)
            await self._tool_manager.for_run_step(ctx)
            tool_definitions = [tool.tool_def for tool in (self._tool_manager.tools or {}).values()]
            request_params = ModelRequestParameters(function_tools=tool_definitions)

            model_settings = kwargs.get("model_settings")
            messages_to_send = list(messages)

            if self.callbacks and self.callbacks.before_llm_call:
                result = await _invoke(self.callbacks.before_llm_call, messages_to_send, model_settings)
                if result is not None:
                    messages_to_send, model_settings = result

            response: ModelResponse = await self.model.request(
                messages=messages_to_send,
                model_settings=model_settings,
                model_request_parameters=request_params,
            )

            if self.callbacks and self.callbacks.after_llm_call:
                result = await _invoke(self.callbacks.after_llm_call, response)
                if result is not None:
                    response = result

            assistant_parts: list[TextPart | ToolCallPart] = []
            if response.text:
                assistant_parts.append(TextPart(content=response.text))
            for tool_call in response.tool_calls or []:
                assistant_parts.append(
                    ToolCallPart(
                        tool_call_id=tool_call.get("id", ""),
                        tool_name=tool_call["name"],
                        args=tool_call.get("arguments", "{}"),
                    )
                )
            if not assistant_parts:
                assistant_parts.append(TextPart(content=""))
            messages.append(ModelMessage(role="assistant", parts=assistant_parts))

            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call.get("arguments", "{}")
                    try:
                        if self.callbacks and self.callbacks.before_tool_call:
                            result = await _invoke(self.callbacks.before_tool_call, tool_name, tool_args, ctx)
                            if result is not None:
                                tool_name, tool_args = result

                        tool_result = await self._tool_manager.handle_call(
                            tool_name=tool_name,
                            tool_args_json=tool_args,
                        )
                        content = str(tool_result)

                        if self.callbacks and self.callbacks.after_tool_call:
                            result = await _invoke(
                                self.callbacks.after_tool_call, tool_name, tool_args, tool_result, ctx
                            )
                            if result is not None:
                                content = str(result)
                    except Exception as exc:
                        content = f"Error: {exc}"

                    messages.append(
                        ModelMessage(
                            role="tool",
                            parts=[
                                ToolReturnPart(
                                    tool_call_id=tool_call.get("id", ""),
                                    content=content,
                                )
                            ],
                        )
                    )
                continue
            else:
                if message_history is not None:
                    message_history.extend(messages[history_start:])
                if self.history is not None and session_id is not None:
                    await self.history.save(session_id, messages[save_from:])
                return response.text  # type: ignore

        if message_history is not None:
            message_history.extend(messages[history_start:])
        if self.history is not None and session_id is not None:
            await self.history.save(session_id, messages[save_from:])
        return response.text  # type: ignore

    async def run_stream_events(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        session_id: str | None = None,
        message_history: list[ModelMessage] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[NativeEvent]:
        if input_data is None:
            input_data = ""

        loaded_history: list[ModelMessage] | None = None
        if self.history is not None and session_id is not None:
            loaded_history = await self.history.load(session_id)

        effective_history = message_history if message_history is not None else loaded_history
        messages = self._build_messages(input_data, effective_history)
        history_start = len(messages) - 1
        save_from = 1 if self.system_prompt else 0
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            ctx = RunContext(deps=deps)
            await self._tool_manager.for_run_step(ctx)
            tool_definitions = [tool.tool_def for tool in (self._tool_manager.tools or {}).values()]
            request_params = ModelRequestParameters(function_tools=tool_definitions)

            model_settings = kwargs.get("model_settings")
            messages_to_send = list(messages)

            if self.callbacks and self.callbacks.before_llm_call:
                result = await _invoke(self.callbacks.before_llm_call, messages_to_send, model_settings)
                if result is not None:
                    messages_to_send, model_settings = result

            parts_by_index: dict[int, TextPart | ToolCallPart] = {}
            async for event in self.model.request_stream(
                messages=messages_to_send,
                model_settings=model_settings,
                model_request_parameters=request_params,
            ):
                yield event
                if isinstance(event, PartEndEvent) and event.part is not None:
                    if isinstance(event.part, (TextPart, ToolCallPart)):
                        parts_by_index[event.index] = event.part

            assistant_parts: list[TextPart | ToolCallPart] = [
                parts_by_index[i] for i in sorted(parts_by_index) if parts_by_index[i] is not None
            ]
            if not assistant_parts:
                assistant_parts.append(TextPart(content=""))
            messages.append(ModelMessage(role="assistant", parts=assistant_parts))

            tool_calls = [p for p in assistant_parts if isinstance(p, ToolCallPart)]
            if not tool_calls:
                text = "".join(p.content for p in assistant_parts if isinstance(p, TextPart))
                if self.callbacks and self.callbacks.after_llm_call:
                    pass  # streaming already yielded; after_llm_call only applies to non-streaming
                if message_history is not None:
                    message_history.extend(messages[history_start:])
                if self.history is not None and session_id is not None:
                    await self.history.save(session_id, messages[save_from:])
                yield AgentRunResultEvent(result=AgentRunResult(output=text or ""))
                return

            for tool_call in tool_calls:
                tool_name = tool_call.tool_name
                tool_args = tool_call.args
                try:
                    if self.callbacks and self.callbacks.before_tool_call:
                        result = await _invoke(self.callbacks.before_tool_call, tool_name, tool_args, ctx)
                        if result is not None:
                            tool_name, tool_args = result

                    tool_result = await self._tool_manager.handle_call(
                        tool_name=tool_name,
                        tool_args_json=tool_args,
                    )
                    content = str(tool_result)

                    if self.callbacks and self.callbacks.after_tool_call:
                        result = await _invoke(self.callbacks.after_tool_call, tool_name, tool_args, tool_result, ctx)
                        if result is not None:
                            content = str(result)
                except Exception as exc:
                    content = f"Error: {exc}"

                yield ToolResultEvent(tool_call_id=tool_call.tool_call_id, content=content)
                messages.append(
                    ModelMessage(
                        role="tool",
                        parts=[ToolReturnPart(tool_call_id=tool_call.tool_call_id, content=content)],
                    )
                )

        if message_history is not None:
            message_history.extend(messages[history_start:])
        if self.history is not None and session_id is not None:
            await self.history.save(session_id, messages[save_from:])
        last_parts = messages[-1].parts if messages else []
        text = "".join(p.content for p in last_parts if isinstance(p, TextPart))
        yield AgentRunResultEvent(result=AgentRunResult(output=text or ""))

    @asynccontextmanager
    async def iter(
        self,
        input_data: str | Sequence[UserContent] | None = None,
        *,
        deps: AgentDepsT = None,
        session_id: str | None = None,
        message_history: list[ModelMessage] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        async def _run_steps() -> AsyncIterator[dict[str, Any]]:
            _input = input_data if input_data is not None else ""

            loaded_history: list[ModelMessage] | None = None
            if self.history is not None and session_id is not None:
                loaded_history = await self.history.load(session_id)

            effective_history = message_history if message_history is not None else loaded_history
            messages = self._build_messages(_input, effective_history)
            history_start = len(messages) - 1
            save_from = 1 if self.system_prompt else 0
            max_iterations = 10
            last_text = ""

            for iteration in range(max_iterations):
                ctx = RunContext(deps=deps, step=iteration)
                await self._tool_manager.for_run_step(ctx)
                tool_definitions = [tool.tool_def for tool in (self._tool_manager.tools or {}).values()]
                request_params = ModelRequestParameters(function_tools=tool_definitions)

                model_settings = kwargs.get("model_settings")
                messages_to_send = list(messages)

                if self.callbacks and self.callbacks.before_llm_call:
                    result = await _invoke(self.callbacks.before_llm_call, messages_to_send, model_settings)
                    if result is not None:
                        messages_to_send, model_settings = result

                response: ModelResponse = await self.model.request(
                    messages=messages_to_send,
                    model_settings=model_settings,
                    model_request_parameters=request_params,
                )
                last_text = response.text or ""

                if self.callbacks and self.callbacks.after_llm_call:
                    cb_result = await _invoke(self.callbacks.after_llm_call, response)
                    if cb_result is not None:
                        response = cb_result
                        last_text = response.text or ""

                yield {
                    "step": "model_response",
                    "iteration": iteration,
                    "text": last_text,
                    "tool_calls": response.tool_calls or [],
                }

                assistant_parts: list[TextPart | ToolCallPart] = []
                if response.text:
                    assistant_parts.append(TextPart(content=response.text))
                for tc in response.tool_calls or []:
                    assistant_parts.append(
                        ToolCallPart(
                            tool_call_id=tc.get("id", ""),
                            tool_name=tc["name"],
                            args=tc.get("arguments", "{}"),
                        )
                    )
                if not assistant_parts:
                    assistant_parts.append(TextPart(content=""))
                messages.append(ModelMessage(role="assistant", parts=assistant_parts))

                if response.tool_calls:
                    for tc in response.tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc.get("arguments", "{}")
                        try:
                            if self.callbacks and self.callbacks.before_tool_call:
                                result = await _invoke(self.callbacks.before_tool_call, tool_name, tool_args, ctx)
                                if result is not None:
                                    tool_name, tool_args = result

                            tool_result = await self._tool_manager.handle_call(
                                tool_name=tool_name,
                                tool_args_json=tool_args,
                            )
                            content = str(tool_result)

                            if self.callbacks and self.callbacks.after_tool_call:
                                result = await _invoke(
                                    self.callbacks.after_tool_call, tool_name, tool_args, tool_result, ctx
                                )
                                if result is not None:
                                    content = str(result)
                        except Exception as exc:
                            content = f"Error: {exc}"

                        yield {
                            "step": "tool_result",
                            "tool_name": tc["name"],
                            "tool_call_id": tc.get("id", ""),
                            "result": content,
                        }
                        messages.append(
                            ModelMessage(
                                role="tool",
                                parts=[ToolReturnPart(tool_call_id=tc.get("id", ""), content=content)],
                            )
                        )
                    continue

                if message_history is not None:
                    message_history.extend(messages[history_start:])
                if self.history is not None and session_id is not None:
                    await self.history.save(session_id, messages[save_from:])
                yield {"step": "complete", "result": last_text}
                return

            if message_history is not None:
                message_history.extend(messages[history_start:])
            if self.history is not None and session_id is not None:
                await self.history.save(session_id, messages[save_from:])
            yield {"step": "complete", "result": last_text}

        yield _run_steps()

    async def __aenter__(self) -> MindtraceAgent[AgentDepsT, OutputDataT]:
        async with self._lock:
            self._entered_count += 1
        return self

    async def __aexit__(self, *args: Any) -> bool | None:
        async with self._lock:
            self._entered_count -= 1
        return None


__all__ = [
    "AgentDepsT",
    "MindtraceAgent",
]
