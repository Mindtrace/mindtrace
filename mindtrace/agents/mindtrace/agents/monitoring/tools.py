"""Agent tools for querying and controlling Mindtrace services.

Each tool follows the existing RunContext[Deps] pattern used throughout
the mindtrace agents framework. Sync tools return immediately; async tools
are used for operations that involve network I/O (heartbeat, restart).

All return values are plain strings — easy for LLMs to parse and relay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

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
    error_store: Any = field(default=None)  # Optional[ErrorFileStore]


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
    min_severity: str = "debug",
) -> str:
    """Return recent log events for a specific service, including heartbeats and
    application log lines streamed from the service's structlog file.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of events to return (default 50).
        min_severity: Minimum severity level — debug | info | warning | error | critical.
                      Defaults to debug so all events including heartbeats are visible.
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

    from mindtrace.services.monitoring.memory import EventType
    lines = [f"Last {len(events)} events for '{service_name}' (severity >= {min_severity}):"]
    for e in events:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        # For tailed application log lines use "log" label; others use the event type
        label = "log" if e.event_type == EventType.NOTIFICATION else e.event_type.value
        details_str = f" | {json.dumps(e.details)}" if e.details else ""
        lines.append(
            f"  [{ts}] {e.severity.value.upper():8s} {label}: "
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


# ---------------------------------------------------------------------------
# JSONL error log tools (only useful when error_log_dir was configured)
# ---------------------------------------------------------------------------


def search_error_logs(
    ctx: RunContext[MonitoringDeps],
    service_name: Optional[str] = None,
    since_hours: float = 24.0,
    limit: int = 20,
) -> str:
    """Search JSONL error log files for recent endpoint errors with full traceback
    and code context showing exactly where in the source code each error originated.

    Args:
        service_name: Filter to one service (omit for all services).
        since_hours: Look back this many hours (default 24).
        limit: Maximum number of error records to return (default 20).
    """
    from mindtrace.services.monitoring.error_store import ErrorFileStore

    # Build a list of (store, filter_name) from per-service dirs in the registry
    log_dirs = ctx.deps.monitor.all_error_log_dirs()
    if service_name:
        d = ctx.deps.monitor.get_service_error_log_dir(service_name)
        log_dirs = {service_name: d} if d else {}

    # Also include the supervisor-level store if present (legacy path)
    stores: list[tuple[Any, Optional[str]]] = []
    if ctx.deps.error_store is not None:
        stores.append((ctx.deps.error_store, service_name))
    for svc, d in log_dirs.items():
        if d:
            try:
                stores.append((ErrorFileStore(base_dir=d), svc if not service_name else service_name))
            except Exception:
                pass

    if not stores:
        return (
            "No JSONL error logs found. Set env variable MINDTRACE_DIR_PATHS__ERROR_LOG_DIR"
            "so it writes errors locally; the path is reported to the supervisor on registration."
        )

    records = []
    for store, filter_name in stores:
        records.extend(store.iter_records(
            service_name=filter_name,
            since_hours=since_hours,
            limit=limit,
        ))
    # Sort newest first and cap at limit
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    records = records[:limit]

    scope = f"'{service_name}'" if service_name else "all services"
    if not records:
        return f"No error records found in the last {since_hours:.0f}h for {scope}."

    lines = [f"{len(records)} error(s) in last {since_hours:.0f}h for {scope}:"]
    for rec in records:
        ts = rec.get("ts", "unknown")
        svc = rec.get("service", "?")
        op = rec.get("operation", "?")
        etype = rec.get("error_type", "?")
        emsg = rec.get("error_message", "")
        ms = rec.get("duration_ms", 0)

        lines.append(f"\n[{ts}] {svc}.{op} ({etype}) — {ms:.1f}ms")
        lines.append(f"  Message: {emsg}")

        ctx_info = rec.get("code_context")
        if ctx_info:
            rel_file = ctx_info.get("file", "")
            # Show path relative to repo root if possible
            try:
                from pathlib import Path
                rel_file = str(Path(rel_file).resolve())
            except Exception:
                pass
            lines.append(
                f"  Location: {rel_file}:{ctx_info.get('lineno')} "
                f"in {ctx_info.get('function')}()"
            )
            snippet = ctx_info.get("snippet", "")
            if snippet:
                lines.append("  Code:")
                for snippet_line in snippet.splitlines():
                    lines.append(f"    {snippet_line}")

        tb = rec.get("traceback", "")
        if tb:
            # Show only the last 3 lines of the traceback to keep output compact
            tb_lines = [l for l in tb.splitlines() if l.strip()]
            lines.append(f"  Traceback (last {min(3, len(tb_lines))} lines):")
            for tb_line in tb_lines[-3:]:
                lines.append(f"    {tb_line}")

    return "\n".join(lines)


def list_error_sessions(
    ctx: RunContext[MonitoringDeps],
) -> str:
    """List all available JSONL error log sessions per service with their date,
    file count, size, and total number of recorded errors.
    """
    from mindtrace.services.monitoring.error_store import ErrorFileStore

    all_dirs: dict[str, str] = ctx.deps.monitor.all_error_log_dirs()
    if ctx.deps.error_store is not None:
        all_dirs["_supervisor"] = ""  # sentinel — use ctx.deps.error_store

    if not all_dirs:
        return (
            "No JSONL error log directories registered. "
            "Set env variable MINDTRACE_DIR_PATHS__ERROR_LOG_DIR to enable error logging."
        )

    lines = []
    for svc_name, log_dir in all_dirs.items():
        if svc_name == "_supervisor" and ctx.deps.error_store is not None:
            store = ctx.deps.error_store
        elif log_dir:
            try:
                store = ErrorFileStore(base_dir=log_dir)
            except Exception:
                continue
        else:
            continue

        sessions = store.list_sessions()
        if not sessions:
            lines.append(f"{svc_name}: no sessions yet")
            continue
        lines.append(f"{svc_name} ({log_dir or 'supervisor store'}):")
        for s in sessions:
            tag = " ← current" if s["is_current"] else ""
            lines.append(
                f"  {s['session_id']}{tag}: "
                f"{s['total_errors']} error(s), {s['files']} file(s), {s['size_kb']} KB"
            )

    return "\n".join(lines) if lines else "No error log sessions found yet."
