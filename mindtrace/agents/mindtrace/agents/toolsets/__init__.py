from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Generic

from .._run_context import RunContext
from ..tools import ToolAgentDepsT, ToolDefinition
from .function import FunctionToolset, FunctionToolsetTool


@dataclass
class ToolsetTool:
    tool_def: ToolDefinition
    max_retries: int | None


class AbstractToolset(Generic[ToolAgentDepsT]):
    @abstractmethod
    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        raise NotImplementedError

    @abstractmethod
    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ToolAgentDepsT],
        tool: ToolsetTool,
    ) -> Any:
        raise NotImplementedError


__all__ = [
    "AbstractToolset",
    "FunctionToolset",
    "FunctionToolsetTool",
    "ToolsetTool",
]
