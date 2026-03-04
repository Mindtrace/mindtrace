#!/usr/bin/env python3
"""
Demo: ServiceSupervisorAgent with Ollama (local LLM) — launch services, ask questions.

Uses an OpenAI-compatible provider pointing at a local Ollama instance so no
API key is required. Change OLLAMA_MODEL to any model you have pulled locally
(e.g. llama3.2, mistral, qwen2.5, phi3, etc.).

Run Ollama first:
  ollama pull llama3.2
  ollama serve          # starts on http://localhost:11434 by default

Run from the repo root:
  PYTHONPATH=mindtrace/agents:mindtrace/services:mindtrace/core \\
  .venv/bin/python mindtrace/agents/scripts/service_monitor_ollama.py

Optional env vars:
  OLLAMA_BASE_URL  — override Ollama base URL (default http://localhost:11434/v1)
  OLLAMA_MODEL     — override model name (default llama3.2)
"""
from __future__ import annotations

import asyncio
import os
import time

# --- Importing mindtrace.services activates the global monitor automatically. ---
from mindtrace.services import EchoService

from mindtrace.agents.models.openai_chat import OpenAIChatModel
from mindtrace.agents.providers import OllamaProvider
from mindtrace.services.monitoring.supervisor import ServiceSupervisorAgent
from mindtrace.services.monitoring.monitor import get_monitor


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


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
    # ------------------------------------------------------------------
    # 1. Launch a service — monitor picks it up automatically
    # ------------------------------------------------------------------
    _separator("1. Launching EchoService")

    print(f"  Launching EchoService on port 8770 ...")
    try:
        cm = EchoService.launch(port=8770)
    except Exception as e:
        print(f"  ERROR launching service: {e}")
        print("  Make sure the port is free and mindtrace.services is importable.")
        return

    print(f"  EchoService running at {cm.url}")
    time.sleep(0.5)

    # Verify the monitor picked it up
    monitor = get_monitor()
    registered = monitor.registered_services()
    print(f"  Monitor registered services: {registered}")

    # ------------------------------------------------------------------
    # 2. Exercise the service so there are some stats
    # ------------------------------------------------------------------
    _separator("2. Making test calls")

    for i in range(3):
        result = cm.echo(message=f"test message {i}", delay=0)
        print(f"  Call {i+1}: echoed={result.echoed!r}")

    # ------------------------------------------------------------------
    # 3. Create the supervisor agent
    # ------------------------------------------------------------------
    _separator(f"3. Creating ServiceSupervisorAgent (Ollama / {OLLAMA_MODEL})")

    provider = OllamaProvider(base_url=OLLAMA_BASE_URL)
    model = OpenAIChatModel(OLLAMA_MODEL, provider=provider)

    try:
        agent = ServiceSupervisorAgent.create(model=model)
        print("  Agent ready.")
    except Exception as e:
        print(f"  ERROR creating agent: {e}")
        cm.shutdown(block=True)
        return

    # ------------------------------------------------------------------
    # 4. Ask the agent questions (multi-turn)
    # ------------------------------------------------------------------
    _separator("4. Agent Q&A")

    queries = [
        "Which services are registered with the monitor?",
        "What is the current status and how many endpoint calls have been made?",
        "Are there any errors in the last hour?",
    ]

    for query in queries:
        try:
            answer = await agent.run(query)
            _q(query, answer)
        except Exception as e:
            print(f"  [ERROR] {e}")
            print("  (Is Ollama running? Try: ollama serve)")
            break

    # ------------------------------------------------------------------
    # 5. Simulate an issue: inject an error event manually, then ask agent
    # ------------------------------------------------------------------
    _separator("5. Injecting a synthetic error and asking agent to diagnose")

    from datetime import datetime, timezone
    from mindtrace.services.monitoring.memory import EventSeverity, EventType, ServiceEvent
    memory = monitor.memory
    memory.record_event(ServiceEvent(
        timestamp=datetime.now(timezone.utc),
        service_name="EchoService",
        event_type=EventType.ERROR,
        severity=EventSeverity.ERROR,
        message="Simulated: model inference timeout after 30s",
        details={"endpoint": "echo", "timeout_ms": 30000},
    ))
    print("  Injected a synthetic error event into memory.")

    try:
        answer = await agent.run(
            "I think there might be an issue with EchoService. "
            "Can you run a full diagnostic and tell me what you find?"
        )
        _q("Diagnostic report:", answer)

        answer = await agent.run("Should I restart EchoService?")
        _q("Restart recommendation:", answer)
    except Exception as e:
        print(f"  [ERROR] {e}")

    # ------------------------------------------------------------------
    # 6. Clean up
    # ------------------------------------------------------------------
    _separator("6. Clean up")
    print("  Shutting down EchoService ...")
    cm.shutdown(block=True)
    print("  Done.")


if __name__ == "__main__":
    asyncio.run(main())
