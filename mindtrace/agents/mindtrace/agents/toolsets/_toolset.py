from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic

from .._run_context import RunContext
from ..tools import ToolAgentDepsT, ToolDefinition

if TYPE_CHECKING:
    from ._filter import ToolFilter
    from .filtered import FilteredToolset


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

    # ------------------------------------------------------------------
    # Tool visibility — shorthand filter methods
    # ------------------------------------------------------------------

    def include(self, *names: str) -> FilteredToolset:
        """Expose only the named tools from this toolset."""
        from ._filter import ToolFilter
        from .filtered import FilteredToolset

        return FilteredToolset(self, ToolFilter.include(*names))

    def exclude(self, *names: str) -> FilteredToolset:
        """Expose all tools except the named ones."""
        from ._filter import ToolFilter
        from .filtered import FilteredToolset

        return FilteredToolset(self, ToolFilter.exclude(*names))

    def include_pattern(self, *patterns: str) -> FilteredToolset:
        """Expose tools whose name matches any glob pattern (e.g. ``"read_*"``)."""
        from ._filter import ToolFilter
        from .filtered import FilteredToolset

        return FilteredToolset(self, ToolFilter.include_pattern(*patterns))

    def exclude_pattern(self, *patterns: str) -> FilteredToolset:
        """Block tools whose name matches any glob pattern."""
        from ._filter import ToolFilter
        from .filtered import FilteredToolset

        return FilteredToolset(self, ToolFilter.exclude_pattern(*patterns))

    def with_filter(self, filter: ToolFilter) -> FilteredToolset:
        """Apply a custom composed ``ToolFilter`` to this toolset."""
        from .filtered import FilteredToolset

        return FilteredToolset(self, filter)


__all__ = [
    "AbstractToolset",
    "ToolsetTool",
]
