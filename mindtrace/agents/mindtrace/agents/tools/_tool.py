from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Concatenate, TypeAlias

from typing_extensions import ParamSpec, TypeVar

from .._run_context import AgentDepsT, RunContext
from .._function_schema import FunctionSchema, function_schema

ToolParams = ParamSpec("ToolParams")
ToolAgentDepsT = TypeVar("ToolAgentDepsT")

ToolFuncContext: TypeAlias = Callable[Concatenate[RunContext[Any], ToolParams], Any]
ToolFuncPlain: TypeAlias = Callable[ToolParams, Any]
ToolFuncEither: TypeAlias = ToolFuncContext[ToolParams] | ToolFuncPlain[ToolParams]


@dataclass(init=False)
class Tool(object):
    function: Callable[..., Any]
    function_schema: FunctionSchema
    name: str
    description: str | None
    max_retries: int | None = None

    def __init__(
        self,
        function: Callable[..., Any],
        *,
        takes_ctx: bool | None = None,
        name: str | None = None,
        description: str | None = None,
        max_retries: int | None = None,
        function_schema_obj: FunctionSchema | None = None,
    ):
        self.function = function
        self.function_schema = function_schema_obj or function_schema(function, takes_ctx=takes_ctx)
        self.name = name or function.__name__
        self.description = description or self.function_schema.description
        self.max_retries = max_retries

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.function(*args, **kwargs)

    def tool_def(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.function_schema.parameters_json_schema(),
        )


@dataclass
class ToolDefinition:
    name: str
    parameters_json_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )
    description: str | None = None
    strict: bool | None = None
    kind: str = "function"


__all__ = [
    "Tool",
    "ToolAgentDepsT",
    "ToolDefinition",
    "ToolFuncContext",
    "ToolFuncEither",
    "ToolFuncPlain",
    "ToolParams",
]
