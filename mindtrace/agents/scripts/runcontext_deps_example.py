#!/usr/bin/env python3
"""
Demonstrates how to use RunContext and deps with MindtraceAgent.

deps are passed at call time (not at agent construction), so the same agent
can serve different users / contexts by passing different deps each run.

Run from the repo root:
  PYTHONPATH=mindtrace/agents python mindtrace/agents/scripts/runcontext_deps_example.py
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from mindtrace.agents._run_context import RunContext
from mindtrace.agents.core.base import MindtraceAgent
from mindtrace.agents.models.gemini import GeminiModel
from mindtrace.agents.tools._tool import Tool


# ---------------------------------------------------------------------------
# 1. Define your deps — anything the tools need at runtime
# ---------------------------------------------------------------------------

@dataclass
class AppDeps:
    user_id: str
    role: str          # e.g. "admin" or "viewer"
    api_token: str


# ---------------------------------------------------------------------------
# 2. Tools that use RunContext to access deps
# ---------------------------------------------------------------------------

def get_user_profile(_ctx: RunContext[AppDeps], field: str) -> str:
    """Return a field from the current user's profile (id, role)."""
    user = _ctx.deps.user_id
    role = _ctx.deps.role
    data = {"id": user, "role": role}
    return data.get(field, f"unknown field '{field}'")


def restricted_action(_ctx: RunContext[AppDeps], action: str) -> str:
    """Perform an action that requires admin role."""
    if _ctx.deps.role != "admin":
        return f"Access denied: user '{_ctx.deps.user_id}' does not have admin rights."
    return f"Action '{action}' executed successfully by admin '{_ctx.deps.user_id}'."


def get_retry_info(_ctx: RunContext[AppDeps]) -> str:
    """Return current step and retry count from the run context."""
    return f"step={_ctx.step}, retry={_ctx.retry}"


# ---------------------------------------------------------------------------
# 3. Build the agent once — reused across different deps
# ---------------------------------------------------------------------------

model = GeminiModel(
    model_id="gemini-2.5-flash",
    client_args={
        "api_key": os.getenv("GEMINI_API_KEY", "AIzaSyDLKxku5eysYGYbJ4sHIYvCpcB8hFNrOLQ"),
    },
)

agent = MindtraceAgent(
    model=model,
    tools=[
        Tool(get_user_profile),
        Tool(restricted_action),
        Tool(get_retry_info),
    ],
)
agent.name = "deps_demo_agent"


# ---------------------------------------------------------------------------
# 4. Run with different deps — same agent, different users
# ---------------------------------------------------------------------------

async def demo_viewer() -> None:
    print("=== Viewer user (read-only) ===\n")
    deps = AppDeps(user_id="alice", role="viewer", api_token="tok_alice")

    result = await agent.run(
        "What is my user id and role? Also try to delete all records.",
        deps=deps,
    )
    print(f"Response: {result}\n")


async def demo_admin() -> None:
    print("=== Admin user ===\n")
    deps = AppDeps(user_id="bob", role="admin", api_token="tok_bob")

    result = await agent.run(
        "What is my user id and role? Also delete all records.",
        deps=deps,
    )
    print(f"Response: {result}\n")


async def demo_stream_with_deps() -> None:
    from mindtrace.agents.events import (
        AgentRunResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
        TextPartDelta,
        ToolResultEvent,
    )

    print("=== Streaming with deps ===\n")
    deps = AppDeps(user_id="carol", role="admin", api_token="tok_carol")

    async for event in agent.run_stream_events(
        "Who am I and what is my current step and retry count?",
        deps=deps,
    ):
        if isinstance(event, PartStartEvent):
            print(f"  [start] {event.part_kind}")
        elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            print(event.delta.content_delta, end="", flush=True)
        elif isinstance(event, PartEndEvent) and event.part_kind == "text":
            print()
        elif isinstance(event, ToolResultEvent):
            print(f"  [tool result] → {event.content}")
        elif isinstance(event, AgentRunResultEvent):
            print(f"\n  [done] {event.result.output!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    await demo_viewer()
    await demo_admin()
    await demo_stream_with_deps()


if __name__ == "__main__":
    asyncio.run(main())
