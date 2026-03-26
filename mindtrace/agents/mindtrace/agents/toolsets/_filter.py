from __future__ import annotations

import fnmatch
from typing import Callable


class ToolFilter:
    """
    Predicate over tool name and description.

    Compose filters with ``&`` (AND), ``|`` (OR), ``~`` (NOT).
    Prefer the shorthand methods on any toolset (``.include()``, ``.exclude()``,
    ``.include_pattern()``, ``.exclude_pattern()``) over constructing this directly.
    Use ``ToolFilter`` directly only when you need boolean composition.

    Example::

        from mindtrace.agents.toolsets import ToolFilter

        # Only read ops, but never the credentials one
        f = ToolFilter.include_pattern("read_*") & ~ToolFilter.include("read_credentials")
        toolset = MCPToolset.from_http(url).with_filter(f)
    """

    def __init__(self, predicate: Callable[[str, str | None], bool]) -> None:
        self._predicate = predicate

    def allows(self, name: str, description: str | None = None) -> bool:
        return self._predicate(name, description)

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def __and__(self, other: ToolFilter) -> ToolFilter:
        return ToolFilter(lambda n, d: self.allows(n, d) and other.allows(n, d))

    def __or__(self, other: ToolFilter) -> ToolFilter:
        return ToolFilter(lambda n, d: self.allows(n, d) or other.allows(n, d))

    def __invert__(self) -> ToolFilter:
        return ToolFilter(lambda n, d: not self.allows(n, d))

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def include(cls, *names: str) -> ToolFilter:
        """Allow only tools whose name is in ``names``."""
        allowed = frozenset(names)
        return cls(lambda n, d: n in allowed)

    @classmethod
    def exclude(cls, *names: str) -> ToolFilter:
        """Allow all tools except those in ``names``."""
        blocked = frozenset(names)
        return cls(lambda n, d: n not in blocked)

    @classmethod
    def include_pattern(cls, *patterns: str) -> ToolFilter:
        """Allow tools whose name matches any glob pattern (e.g. ``"read_*"``)."""
        return cls(lambda n, d: any(fnmatch.fnmatch(n, p) for p in patterns))

    @classmethod
    def exclude_pattern(cls, *patterns: str) -> ToolFilter:
        """Block tools whose name matches any glob pattern."""
        return cls(lambda n, d: not any(fnmatch.fnmatch(n, p) for p in patterns))

    @classmethod
    def by_description(cls, predicate: Callable[[str | None], bool]) -> ToolFilter:
        """Filter on description text — useful when names are not descriptive."""
        return cls(lambda n, d: predicate(d))


__all__ = ["ToolFilter"]
