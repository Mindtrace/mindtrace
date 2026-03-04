"""Agent tools for querying and controlling Mindtrace services.

Each tool follows the existing RunContext[Deps] pattern used throughout
the mindtrace agents framework. Sync tools return immediately; async tools
are used for operations that involve network I/O (heartbeat, restart).

All return values are plain strings — easy for LLMs to parse and relay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from mindtrace.agents._run_context import RunContext
from mindtrace.services.monitoring.memory import EventSeverity, ServiceSessionMemory
from mindtrace.services.monitoring.monitor import ServiceMonitor


# ---------------------------------------------------------------------------
# Dependency container injected into every tool via RunContext
# ---------------------------------------------------------------------------


@dataclass
class MonitoringDeps:
    """Injected into all monitoring agent tools via RunContext.deps."""

    monitor: ServiceMonitor
    memory: ServiceSessionMemory


# ---------------------------------------------------------------------------
# Read-only tools (sync — no I/O)
# ---------------------------------------------------------------------------


def list_registered_services(ctx: RunContext[MonitoringDeps]) -> str:
    """List all service names that are currently registered with the monitor."""
    names = ctx.deps.monitor.registered_services()
    if not names:
        return "No services are registered with the monitor yet."
    return f"Registered services ({len(names)}): {', '.join(names)}"


def get_services_status(ctx: RunContext[MonitoringDeps]) -> str:
    """Return a summary of all registered services with their current status,
    error counts, restart counts, and last heartbeat age."""
    return ctx.deps.memory.summary()


def get_service_logs(
    ctx: RunContext[MonitoringDeps],
    service_name: str,
    limit: int = 50,
    min_severity: str = "info",
) -> str:
    """Return recent log events for a specific service.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of events to return (default 50).
        min_severity: Minimum severity level — debug | info | warning | error | critical.
    """
    try:
        sev = EventSeverity(min_severity.lower())
    except ValueError:
        sev = EventSeverity.INFO

    events = ctx.deps.memory.get_events(
        service_name=service_name,
        min_severity=sev,
        limit=limit,
    )

    if not events:
        return (
            f"No events found for '{service_name}' "
            f"with severity >= {min_severity}. "
            "The service may not be registered or may not have emitted any events yet."
        )

    lines = [f"Last {len(events)} events for '{service_name}' (severity >= {min_severity}):"]
    for e in events:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        details_str = f" | {json.dumps(e.details)}" if e.details else ""
        lines.append(
            f"  [{ts}] {e.severity.value.upper():8s} {e.event_type.value}: "
            f"{e.message}{details_str}"
        )
    return "\n".join(lines)


def get_recent_errors(
    ctx: RunContext[MonitoringDeps],
    service_name: Optional[str] = None,
    since_minutes: int = 60,
) -> str:
    """Return error and critical events, optionally filtered to one service.

    Args:
        service_name: Service name to filter by (omit for all services).
        since_minutes: Look back this many minutes (default 60).
    """
    errors = ctx.deps.memory.get_errors(
        service_name=service_name,
        since_minutes=since_minutes,
    )

    scope = f"'{service_name}'" if service_name else "all services"
    if not errors:
        return f"No errors in the last {since_minutes} minutes for {scope}."

    lines = [f"{len(errors)} error(s) in the last {since_minutes} min for {scope}:"]
    for e in errors:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"  [{ts}] {e.event_type.value}: {e.message}")
        if e.details:
            lines.append(f"    {json.dumps(e.details, indent=4)}")
    return "\n".join(lines)


def get_service_diagnostics(
    ctx: RunContext[MonitoringDeps],
    service_name: str,
) -> str:
    """Return a full diagnostic report for a service: state, error history,
    and recent event log.

    Args:
        service_name: Name of the service to diagnose.
    """
    state = ctx.deps.memory.get_state(service_name)
    if state is None:
        registered = ctx.deps.monitor.registered_services()
        return (
            f"No information found for '{service_name}'. "
            f"Registered services: {', '.join(registered) or 'none'}."
        )

    errors_24h = ctx.deps.memory.get_errors(service_name=service_name, since_minutes=1440)
    recent_events = ctx.deps.memory.get_events(service_name=service_name, limit=20)

    def fmt_dt(dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "unknown"

    lines = [
        f"=== Diagnostic Report: {service_name} ===",
        f"Status      : {state.status}",
        f"URL         : {state.url or 'unknown'}",
        f"Service class: {state.service_class or 'unknown'}",
        f"Launched    : {fmt_dt(state.launch_time)}",
        f"Last seen   : {fmt_dt(state.last_seen)}",
        f"Last heartbeat: {fmt_dt(state.last_heartbeat)}",
        f"Errors (24h): {len(errors_24h)}",
        f"Total errors: {state.error_count}",
        f"Restarts    : {state.restart_count}",
        f"EP calls    : {state.endpoint_calls}",
        f"Consec. HB failures: {state.consecutive_heartbeat_failures}",
    ]

    if state.last_error:
        lines.append(f"Last error  : [{fmt_dt(state.last_error_time)}] {state.last_error}")

    if errors_24h:
        lines.append(f"\nRecent errors (last 5 of {len(errors_24h)}):")
        for e in errors_24h[-5:]:
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            lines.append(f"  [{ts}] {e.message}")
            if e.details:
                lines.append(f"    {json.dumps(e.details)}")

    if recent_events:
        lines.append(f"\nLast {len(recent_events)} events:")
        for e in recent_events:
            ts = e.timestamp.strftime("%H:%M:%S")
            lines.append(
                f"  [{ts}] {e.severity.value.upper():8s} "
                f"{e.event_type.value}: {e.message}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# I/O tools (async — network calls or blocking launches)
# ---------------------------------------------------------------------------


async def check_service_heartbeat(
    ctx: RunContext[MonitoringDeps],
    service_name: str,
) -> str:
    """Perform an immediate live HTTP heartbeat check for a specific service.

    Args:
        service_name: Name of the registered service to check.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    healthy = await loop.run_in_executor(
        None,
        ctx.deps.monitor._check_service_sync,
        service_name,
    )
    state = ctx.deps.memory.get_state(service_name)
    status = state.status if state else "unknown"
    url = state.url if state else "unknown"

    if healthy:
        return (
            f"Service '{service_name}' is healthy.\n"
            f"  Status: {status}\n"
            f"  URL: {url}"
        )
    else:
        last_err = state.last_error if state else "no error recorded"
        failures = state.consecutive_heartbeat_failures if state else 0
        return (
            f"Service '{service_name}' is NOT responding.\n"
            f"  Status: {status}\n"
            f"  URL: {url}\n"
            f"  Consecutive failures: {failures}\n"
            f"  Last error: {last_err}"
        )


async def restart_service(
    ctx: RunContext[MonitoringDeps],
    service_name: str,
) -> str:
    """Gracefully shut down then re-launch a registered service.

    Only works if the service was registered with its service_class.
    If the class is unknown, instructions for manual re-launch are returned.

    Args:
        service_name: Name of the registered service to restart.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        cm = await loop.run_in_executor(
            None,
            ctx.deps.monitor.restart,
            service_name,
        )
        if cm is None:
            return (
                f"'{service_name}' shutdown was requested, but auto-restart is not "
                "possible because service_class was not registered. "
                "Please re-launch the service manually and re-register it."
            )
        state = ctx.deps.memory.get_state(service_name)
        url = state.url if state else "unknown"
        return f"Service '{service_name}' restarted successfully. Now available at {url}."
    except KeyError as exc:
        return f"Cannot restart: {exc}. Use list_registered_services to see valid names."
    except Exception as exc:
        return f"Restart failed for '{service_name}': {exc}"
