from __future__ import annotations

from typing import Any

from .._run_context import RunContext
from ..tools import Tool, ToolAgentDepsT
from ..toolsets._toolset import AbstractToolset, ToolsetTool
from ..toolsets.function import FunctionToolset
from ._store import AbstractMemoryStore


class MemoryToolset(AbstractToolset[ToolAgentDepsT]):
    """Exposes memory operations as agent-native tools.

    The LLM can call save_memory, recall_memory, search_memory,
    forget_memory, and list_memories to manage persistent state.
    """

    def __init__(self, store: AbstractMemoryStore, namespace: str = "default") -> None:
        self._store = store
        self._namespace = namespace
        self._inner = self._build_toolset()

    def _prefixed(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def _strip_prefix(self, key: str) -> str:
        prefix = f"{self._namespace}:"
        return key[len(prefix):] if key.startswith(prefix) else key

    def _build_toolset(self) -> FunctionToolset:
        store = self._store
        prefixed = self._prefixed
        strip = self._strip_prefix
        ns_prefix = f"{self._namespace}:"

        async def save_memory(key: str, value: str) -> str:
            """Store a fact or piece of information for later recall."""
            await store.save(prefixed(key), value)
            return f"Saved: {key}"

        async def recall_memory(key: str) -> str:
            """Retrieve a specific memory by its key."""
            entry = await store.get(prefixed(key))
            return entry.value if entry else f"No memory found for key: {key}"

        async def search_memory(query: str, top_k: int = 5) -> str:
            """Search memories by relevance or keyword."""
            results = await store.search(query, top_k=top_k * 3)
            scoped = [e for e in results if e.key.startswith(ns_prefix)][:top_k]
            if not scoped:
                return "No matching memories found."
            return "\n".join(f"{strip(e.key)}: {e.value}" for e in scoped)

        async def forget_memory(key: str) -> str:
            """Delete a memory entry."""
            await store.delete(prefixed(key))
            return f"Forgot: {key}"

        async def list_memories() -> str:
            """List all stored memory keys."""
            all_keys = await store.list_keys()
            scoped = [strip(k) for k in all_keys if k.startswith(ns_prefix)]
            return "\n".join(scoped) if scoped else "No memories stored."

        toolset = FunctionToolset()
        for fn in [save_memory, recall_memory, search_memory, forget_memory, list_memories]:
            toolset.add_tool(Tool(fn))
        return toolset

    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        return await self._inner.get_tools(ctx)

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ToolAgentDepsT],
        tool: ToolsetTool,
    ) -> Any:
        return await self._inner.call_tool(name, tool_args, ctx, tool)


__all__ = ["MemoryToolset"]
