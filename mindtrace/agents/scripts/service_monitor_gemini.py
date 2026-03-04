#!/usr/bin/env python3
"""
Demo: ServiceSupervisorAgent with Gemini — launch services, ask questions, diagnose issues.

What this script demonstrates:
  1. Importing mindtrace.services activates ambient monitoring automatically.
  2. EchoService.launch() is tracked without any monitor setup code.
  3. ServiceSupervisorAgent answers natural-language queries about running services.
  4. Multi-turn conversation history is maintained across agent.run() calls.
  5. The agent can use tools (list services, get status, diagnose, restart).

Run from the repo root:
  GEMINI_API_KEY=AIza... \\
  PYTHONPATH=mindtrace/agents:mindtrace/services:mindtrace/core \\
  .venv/bin/python mindtrace/agents/scripts/service_monitor_gemini.py

Or with the .venv activated:
  source .venv/bin/activate
  GEMINI_API_KEY=AIza... \\
  PYTHONPATH=mindtrace/agents:mindtrace/services:mindtrace/core \\
  python mindtrace/agents/scripts/service_monitor_gemini.py
"""
from __future__ import annotations

import asyncio
import os
import time

# --- Step 1: import mindtrace.services — this activates the global monitor. ---
# All subsequent EchoService.launch() calls are tracked automatically.
from mindtrace.services import EchoService

from mindtrace.agents.models.gemini import GeminiModel
from mindtrace.services.monitoring.supervisor import ServiceSupervisorAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def _q(label: str, answer: str) -> None:
    print(f"\n>>> {label}")
    print(f"    {answer.strip().replace(chr(10), chr(10) + '    ')}")


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

async def main() -> None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("WARNING: GEMINI_API_KEY not set — Gemini calls will fail.")

    # ------------------------------------------------------------------
    # 1. Launch services (monitor registers them automatically)
    # ------------------------------------------------------------------
    _separator("1. Launching services")

    print("  Launching EchoService on port 8765 ...")
    cm1 = EchoService.launch(port=8765)
    print(f"  EchoService running at {cm1.url}")

    print("  Launching a second EchoService on port 8766 ...")
    cm2 = EchoService.launch(port=8766)
    print(f"  EchoService (2) running at {cm2.url}")

    # Give heartbeat poller a moment to do its first pass
    time.sleep(1)

    # ------------------------------------------------------------------
    # 2. Create the supervisor agent
    # ------------------------------------------------------------------
    _separator("2. Creating ServiceSupervisorAgent (Gemini)")

    model = GeminiModel(
        model_id="gemini-2.5-flash",
        client_args={"api_key": api_key},
    )
    agent = ServiceSupervisorAgent.create(model=model)
    print("  Agent ready.")

    # ------------------------------------------------------------------
    # 3. Multi-turn conversation
    # ------------------------------------------------------------------
    _separator("3. Multi-turn agent Q&A")

    # Turn 1 — service overview
    answer = await agent.run("Which services are currently registered and running?")
    _q("Which services are registered and running?", answer)

    # Turn 2 — follow-up (uses prior context — agent knows we just discussed services)
    answer = await agent.run("Can you give me a quick health summary of all of them?")
    _q("Quick health summary of all of them?", answer)

    # Turn 3 — make an echo call to exercise the service
    print("\n  (Making a live echo call to exercise the service...)")
    result = cm1.echo(message="hello from demo", delay=0)
    print(f"  Echo response: {result}")

    answer = await agent.run(
        "How many endpoint calls has the first EchoService handled? "
        "And are there any errors so far?"
    )
    _q("Endpoint calls and errors?", answer)

    # Turn 4 — shut down one service and ask the agent to notice
    _separator("4. Shutting down one service — agent detects it")
    print("  Shutting down EchoService on port 8765 ...")
    cm1.shutdown(block=True)
    time.sleep(1)   # let heartbeat detect the failure

    answer = await agent.run(
        "One of the services was just stopped. Can you check heartbeat status "
        "and diagnose what happened?"
    )
    _q("Heartbeat / diagnosis after shutdown:", answer)

    # Turn 5 — ask for a restart recommendation
    answer = await agent.run(
        "Based on what you see, should I restart the failed service? "
        "What are your recommended next steps?"
    )
    _q("Restart recommendation:", answer)

    # ------------------------------------------------------------------
    # 5. Clean up
    # ------------------------------------------------------------------
    _separator("5. Clean up")
    print("  Shutting down remaining service ...")
    cm2.shutdown(block=True)
    print("  Done.")


if __name__ == "__main__":
    asyncio.run(main())
