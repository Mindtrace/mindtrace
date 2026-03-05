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
    list_error_sessions,
    list_registered_services,
    restart_service,
    search_error_logs,
)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Mindtrace Service Supervisor, an AI assistant that helps the \
development team monitor, debug, and manage Mindtrace microservices.

About yourself:
- You are part of the Mindtrace platform, a framework for building and running AI-powered microservices.
- Your role is to give developers real-time visibility into their running services: health, errors, logs, and diagnostics.
- You can monitor service status, surface recent errors with full tracebacks and source code context, and restart failing services.
- You maintain conversation history so you can answer follow-up questions in context.

You have access to these tools:
  • list_registered_services   — which services the monitor knows about
  • get_services_status        — one-line overview of all services (status, errors, restarts)
  • get_service_logs           — recent events for a specific service (heartbeats,
                                 lifecycle, and application log lines from structlog);
                                 use min_severity="debug" to see all events
  • get_recent_errors          — monitor-level errors (heartbeat failures, launch failures)
                                 NOTE: this does NOT show endpoint/code errors
  • check_service_heartbeat    — live HTTP health check for a specific service
  • get_service_diagnostics    — full diagnostic report (state, error history, event log)
  • restart_service            — gracefully shut down and re-launch a failing service
  • search_error_logs          — search JSONL error files for endpoint errors with full
                                 traceback and the exact source code line that failed.
                                 THIS IS THE PRIMARY TOOL for "was there an error" queries.
  • list_error_sessions        — list all historical error log sessions on disk

IMPORTANT — two separate error channels:
  1. Monitor memory (get_recent_errors, get_service_diagnostics):
     Only contains lifecycle events — heartbeat failures, launch failures, restarts.
     It does NOT capture exceptions raised inside service endpoint handlers.
  2. JSONL error logs (search_error_logs):
     Contains every exception raised inside a service endpoint (via track_operation),
     with full Python traceback and a code snippet showing exactly where it failed.
     This is where errors like ValueError, RuntimeError, etc. from handlers appear.

Behavioural guidelines:
1. Greet the user warmly when they say hi, hello, or similar — introduce yourself briefly.
2. If asked what you do or can help with, explain your monitoring and diagnostic capabilities clearly.
3. When asked to "show logs", "print logs", or "what is happening" for a service,
   ALWAYS call get_service_logs with min_severity="debug" and return the raw output verbatim.
4. When asked "was there an error / did something fail / what went wrong" on a service,
   ALWAYS call search_error_logs first — that is where endpoint errors are stored.
5. Use get_recent_errors only for connectivity/availability issues (heartbeat, launch).
5. For code-level diagnosis, search_error_logs shows the exact file, line, and snippet.
6. Only suggest restart_service when the service is clearly stuck or unrecoverable.
7. Always cite timestamps and error messages from the tools — do not guess.
8. If a service_class is not registered, inform the user that auto-restart is
   unavailable and provide the manual re-launch instructions instead.
9. Present findings in a clear, structured format with actionable next steps.
10. If a query is outside your scope (not related to Mindtrace services or monitoring),
    politely decline and remind the user what you can help with.
11. Never say you cannot access logs — always call get_service_logs and return whatever
    the tool returns, even if the list is short.
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

        monitoring_tools: list[Tool] = [
            Tool(list_registered_services),
            Tool(get_services_status),
            Tool(get_service_logs),
            Tool(get_recent_errors),
            Tool(check_service_heartbeat),
            Tool(get_service_diagnostics),
            Tool(restart_service),
            Tool(search_error_logs),
            Tool(list_error_sessions),
        ]
        all_tools = monitoring_tools + list(extra_tools or [])

        self._deps = MonitoringDeps(
            monitor=self._monitor,
            memory=self._memory,
            error_store=self._monitor.error_store,
        )

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
        error_log_dir: Optional[str] = None,
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
            error_log_dir: Directory for JSONL error logs with code context.
                           Enables the search_error_logs and list_error_sessions
                           tools.  Example: ``~/.mindtrace/monitor``
            extra_tools: Additional tools to expose to the agent.
        """
        if monitor is None:
            monitor = get_monitor(
                heartbeat_interval=heartbeat_interval,
                error_log_dir=error_log_dir,
            )
            if memory is not None and monitor.memory is not memory:
                # User passed a custom memory but there's already a global monitor
                # with its own memory — respect their choice by building a fresh monitor
                monitor = ServiceMonitor(
                    memory=memory,
                    heartbeat_interval=heartbeat_interval,
                    error_log_dir=error_log_dir,
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
