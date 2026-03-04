"""ServiceSupervisorAgent — a pre-wired MindtraceAgent for service operations.

All monitoring tools are configured automatically. The caller only needs to
supply a model. The global ServiceMonitor is used by default.

Usage::

    from mindtrace.services.monitoring import ServiceSupervisorAgent
    from mindtrace.agents.models import OpenAIChatModel
    from mindtrace.agents.providers import OpenAIProvider

    agent = ServiceSupervisorAgent.create(
        model=OpenAIChatModel("gpt-4o", provider=OpenAIProvider()),
    )

    # Queries
    print(await agent.run("Which services are running?"))
    print(await agent.run("Are there any errors in the last hour?"))
    print(await agent.run("Diagnose the echo service"))
    print(await agent.run("Restart the echo service"))
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from mindtrace.agents.core.base import MindtraceAgent
from mindtrace.agents.tools._tool import Tool
from mindtrace.services.monitoring.memory import ServiceSessionMemory
from mindtrace.services.monitoring.monitor import ServiceMonitor, get_monitor
from mindtrace.services.monitoring.tools import (
    MonitoringDeps,
    check_service_heartbeat,
    get_recent_errors,
    get_service_diagnostics,
    get_service_logs,
    get_services_status,
    list_registered_services,
    restart_service,
)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Mindtrace Service Supervisor, an AI assistant that helps the \
development team monitor, debug, and manage Mindtrace microservices.

You have access to these tools:
  • list_registered_services   — which services the monitor knows about
  • get_services_status        — one-line overview of all services (status, errors, restarts)
  • get_service_logs           — recent events for a specific service
  • get_recent_errors          — errors across all or one service within a time window
  • check_service_heartbeat    — live HTTP health check for a specific service
  • get_service_diagnostics    — full diagnostic report (state, error history, event log)
  • restart_service            — gracefully shut down and re-launch a failing service

Guidelines:
1. Start with get_services_status for an overview before drilling in.
2. Use get_recent_errors and get_service_diagnostics before recommending a restart.
3. Only suggest restart_service when the service is clearly stuck or unrecoverable.
4. Always cite timestamps and error messages from the tools — do not guess.
5. If a service_class is not registered, inform the user that auto-restart is
   unavailable and provide the manual re-launch instructions instead.
6. Present findings in a clear, structured format with actionable next steps.
"""


# ---------------------------------------------------------------------------
# ServiceSupervisorAgent
# ---------------------------------------------------------------------------


class ServiceSupervisorAgent:
    """Pre-wired agent for Mindtrace service monitoring and operations.

    Wraps ``MindtraceAgent`` with all monitoring tools pre-configured.
    Supports both sync (``run_sync``) and async (``run``) execution.

    Args:
        model: Any model compatible with ``MindtraceAgent`` (OpenAI, Gemini, Ollama).
        monitor: ``ServiceMonitor`` instance to use. Defaults to the global monitor.
        extra_tools: Additional ``Tool`` objects to expose to the agent.
    """

    def __init__(
        self,
        model: Any,
        monitor: Optional[ServiceMonitor] = None,
        extra_tools: Optional[Sequence[Tool]] = None,
    ) -> None:
        self._monitor = monitor or get_monitor()
        self._memory = self._monitor.memory
        self._deps = MonitoringDeps(monitor=self._monitor, memory=self._memory)

        monitoring_tools: list[Tool] = [
            Tool(list_registered_services),
            Tool(get_services_status),
            Tool(get_service_logs),
            Tool(get_recent_errors),
            Tool(check_service_heartbeat),
            Tool(get_service_diagnostics),
            Tool(restart_service),
        ]
        all_tools = monitoring_tools + list(extra_tools or [])

        self._message_history: list = []   # persists across run() calls

        self._agent = MindtraceAgent(
            model=model,
            tools=all_tools,
            system_prompt=_SYSTEM_PROMPT,
            _name="service_supervisor",
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        model: Any,
        monitor: Optional[ServiceMonitor] = None,
        memory: Optional[ServiceSessionMemory] = None,
        heartbeat_interval: float = 30.0,
        extra_tools: Optional[Sequence[Tool]] = None,
    ) -> "ServiceSupervisorAgent":
        """Convenience factory.

        Args:
            model: LLM model to use.
            monitor: Existing ``ServiceMonitor`` (uses global monitor if omitted).
            memory: Custom ``ServiceSessionMemory`` — only used when *monitor* is
                    also omitted, to pass a pre-configured memory to ``get_monitor()``.
            heartbeat_interval: Polling interval in seconds (only applied on
                                first call to ``get_monitor()``).
            extra_tools: Additional tools to expose to the agent.
        """
        if monitor is None:
            monitor = get_monitor(heartbeat_interval=heartbeat_interval)
            if memory is not None and monitor.memory is not memory:
                # User passed a custom memory but there's already a global monitor
                # with its own memory — respect their choice by building a fresh monitor
                monitor = ServiceMonitor(
                    memory=memory,
                    heartbeat_interval=heartbeat_interval,
                )
        return cls(model=model, monitor=monitor, extra_tools=extra_tools)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self, query: str, **kwargs: Any) -> str:
        """Run the supervisor agent with a natural-language query.

        Conversation history is maintained automatically across calls so the
        agent has full context of the current session.

        Args:
            query: Natural-language question or instruction from the developer.
            **kwargs: Forwarded to the underlying ``MindtraceAgent.run()``.

        Returns:
            Agent response as a string.
        """
        return await self._agent.run(
            query,
            deps=self._deps,
            message_history=self._message_history,
            **kwargs,
        )

    def run_sync(self, query: str, **kwargs: Any) -> str:
        """Synchronous variant of ``run``.

        Useful in scripts, notebooks, or contexts where an event loop is not
        already running.
        """
        return self._agent.run_sync(
            query,
            deps=self._deps,
            message_history=self._message_history,
            **kwargs,
        )

    def clear_history(self) -> None:
        """Reset the conversation history, starting a fresh session."""
        self._message_history.clear()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def monitor(self) -> ServiceMonitor:
        return self._monitor

    @property
    def memory(self) -> ServiceSessionMemory:
        return self._memory
