from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Generic

from ..tools import ToolAgentDepsT, ToolDefinition
from .._run_context import RunContext


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


from .function import FunctionToolset, FunctionToolsetTool

__all__ = [
    "AbstractToolset",
    "FunctionToolset",
    "FunctionToolsetTool",
    "ToolsetTool",
]
