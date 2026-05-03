from __future__ import annotations

from abc import abstractmethod
from typing import Any

from ..toolsets._toolset import AbstractToolset
from ..tools import ToolAgentDepsT


class AbstractSkill(AbstractToolset[ToolAgentDepsT]):
    """Base class for skill plugins.

    Extends AbstractToolset so skills are drop-in toolsets with no agent-side changes.
    Register via pyproject.toml entry-points:
        [project.entry-points."mindtrace.skills"]
        my_skill = "my_package.skills:MySkill"
    """

    @property
    @abstractmethod
    def skill_name(self) -> str: ...

    @property
    @abstractmethod
    def skill_version(self) -> str: ...

    @property
    def skill_description(self) -> str:
        return ""

    async def setup(self) -> None:
        """Called once by MindtracePluginRegistry after discovery."""

    async def teardown(self) -> None:
        """Called on worker shutdown."""

    async def get_tools(self, ctx: Any) -> dict[str, Any]:
        return {}

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: Any, tool: Any) -> Any:
        raise NotImplementedError(f"Skill {self.skill_name!r} does not implement call_tool for {name!r}")


__all__ = ["AbstractSkill"]
