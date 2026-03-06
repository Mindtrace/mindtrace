"""ServiceLauncherAgent — discovers available Mindtrace services and launches them.

Discovery works in two phases:
1. Walk configurable root package namespaces (default: ["mindtrace.services"]) to
   trigger imports, so Python's subclass registry is populated.
2. Recurse Service.__subclasses__() to collect every concrete subclass — this
   catches classes from any package that has been imported, not just mindtrace.services.

The agent never starts a service without user confirmation. The flow is:
  list_available_services → show catalog → user picks one → start_service
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from mindtrace.agents._run_context import RunContext
from urllib.parse import urlparse

logger = logging.getLogger("mindtrace.agents.launcher")

# Modules whose names indicate internal / non-user-facing code — skip them
_SKIP_PARTS = {"core", "monitoring", "base", "mixin", "connection", "gateway", "test", "tests"}

# ---------------------------------------------------------------------------
# Catalog entry
# ---------------------------------------------------------------------------


@dataclass
class CatalogEntry:
    name: str           # e.g. "EchoService"
    module: str         # e.g. "mindtrace.services.samples.echo_service"
    description: str    # one-line description
    default_port: Optional[int] = None


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _all_subclasses(cls: type) -> list[type]:
    """Recursively collect all non-abstract subclasses of *cls*."""
    result = []
    for sub in cls.__subclasses__():
        if not inspect.isabstract(sub):
            result.append(sub)
        result.extend(_all_subclasses(sub))
    return result


def _infer_description(cls_name: str) -> str:
    """'EchoService' → 'Echo microservice.'"""
    words: list[str] = []
    current: list[str] = []
    for ch in cls_name:
        if ch.isupper() and current:
            words.append("".join(current))
            current = [ch]
        else:
            current.append(ch)
    if current:
        words.append("".join(current))
    label = " ".join(w for w in words if w.lower() != "service")
    return f"{label} microservice."


def _walk_and_import(roots: list[str]) -> None:
    """Import every module under each root namespace to populate __subclasses__."""
    for root in roots:
        try:
            pkg = importlib.import_module(root)
        except ImportError:
            logger.debug("scan_services: cannot import root %s — skipping.", root)
            continue

        for _importer, modname, _ispkg in pkgutil.walk_packages(
            path=getattr(pkg, "__path__", []),
            prefix=root + ".",
            onerror=lambda _: None,
        ):
            parts = modname.split(".")
            if any(skip in parts for skip in _SKIP_PARTS):
                continue
            try:
                importlib.import_module(modname)
            except Exception:
                pass  # import errors in user code should not crash discovery


def scan_services(roots: list[str] | None = None) -> dict[str, CatalogEntry]:
    """Discover all concrete Service subclasses across *roots* namespaces.

    Args:
        roots: List of importable package names to walk. Defaults to
               ``["mindtrace.services"]``. Any package can be added here —
               classes already imported into the process are also captured
               via ``Service.__subclasses__()`` without needing to be in roots.

    Returns:
        Dict mapping class name → CatalogEntry.
    """
    if roots is None:
        roots = ["mindtrace.services"]

    try:
        from mindtrace.services.core.service import Service
    except ImportError:
        logger.warning("scan_services: mindtrace-services is not installed.")
        return {}

    # Phase 1 — trigger imports so __subclasses__ is fully populated
    _walk_and_import(roots)

    # Phase 2 — collect every concrete subclass regardless of origin package
    catalog: dict[str, CatalogEntry] = {}
    for cls in _all_subclasses(Service):
        # Skip classes whose module looks internal
        mod_parts = cls.__module__.split(".")
        if any(skip in mod_parts for skip in _SKIP_PARTS):
            continue

        name = cls.__name__

        # Use only the class's own __doc__, not inherited ones (inspect.getdoc walks MRO)
        own_doc = cls.__dict__.get("__doc__") or ""
        description = next(
            (ln.strip() for ln in own_doc.splitlines() if ln.strip()),
            _infer_description(name),
        )

        default_port: Optional[int] = None
        try:
            url = str(cls.default_url())
            default_port = urlparse(url).port
        except Exception:
            pass

        catalog[name] = CatalogEntry(
            name=name,
            module=cls.__module__,
            description=description,
            default_port=default_port,
        )

    return catalog


# ---------------------------------------------------------------------------
# Agent deps + tools
# ---------------------------------------------------------------------------


@dataclass
class LauncherDeps:
    catalog: dict[str, CatalogEntry] = field(default_factory=dict)


def list_available_services(ctx: RunContext[LauncherDeps]) -> str:
    """List all discovered Mindtrace services with descriptions and default ports.
    Call this when the user asks what services are available or what can be started.
    """
    catalog: dict[str, CatalogEntry] = ctx.deps.catalog
    if not catalog:
        return (
            "No services found. Make sure mindtrace-services is installed and "
            "at least one concrete Service subclass exists."
        )
    lines = [f"Found **{len(catalog)}** available service(s):\n"]
    for entry in sorted(catalog.values(), key=lambda e: e.name):
        port_str = f" _(default port {entry.default_port})_" if entry.default_port else ""
        lines.append(f"• **{entry.name}**{port_str}")
        lines.append(f"  {entry.description}")
        lines.append(f"  `{entry.module}`")
    lines.append("\nWould you like to start any of these?")
    return "\n".join(lines)


async def start_service(
    ctx: RunContext[LauncherDeps],
    service_name: str,
    port: Optional[int] = None,
    host: str = "localhost",
) -> str:
    """Launch a service from the catalog. Only call this after the user has
    explicitly confirmed they want to start the named service.

    Args:
        service_name: Exact name from the catalog (e.g. "EchoService").
        port: Port to listen on. Uses the service default if omitted.
        host: Hostname/IP to bind (default: localhost).
    """
    import asyncio

    catalog: dict[str, CatalogEntry] = ctx.deps.catalog
    entry = catalog.get(service_name)
    if entry is None:
        available = ", ".join(sorted(catalog.keys())) or "none"
        return (
            f"'{service_name}' is not in the catalog. "
            f"Known services: {available}. "
            "Try list_available_services to see the full list."
        )

    try:
        mod = importlib.import_module(entry.module)
        cls = getattr(mod, entry.name)
    except Exception as exc:
        return f"Could not import {entry.module}.{entry.name}: {exc}"

    launch_port = port or entry.default_port
    kwargs: dict[str, Any] = {"host": host}
    if launch_port:
        kwargs["port"] = launch_port

    try:
        loop = asyncio.get_event_loop()
        cm = await loop.run_in_executor(None, lambda: cls.launch(**kwargs))
        url = str(cm.url) if cm else f"http://{host}:{launch_port}"
        return (
            f"**{service_name}** is now running.\n"
            f"URL: `{url}`\n"
            "You can ask the supervisor agent to check its status."
        )
    except Exception as exc:
        return f"Failed to start '{service_name}': {exc}"


# ---------------------------------------------------------------------------
# ServiceLauncherAgent
# ---------------------------------------------------------------------------

_LAUNCHER_PROMPT = """\
You are the Mindtrace Service Launcher. Your job is to help developers
discover and start available Mindtrace microservices.

Strict workflow:
1. When asked what services are available, what can be run, or anything similar —
   ALWAYS call list_available_services first and return its output verbatim.
2. After showing the catalog, ask the user which service they want to start
   and on which port (if they have not already said).
3. ONLY call start_service after the user explicitly confirms with a service name.
   Never launch anything without confirmation.
4. After a successful start, report the URL and tell the user the supervisor agent
   can now monitor it.
5. If asked about something unrelated to discovering or starting services,
   politely say that is outside your scope.
"""


class ServiceLauncherAgent:
    """Discovers all concrete Service subclasses and launches them on request.

    Scans the given root package namespaces once at init. Also captures any
    Service subclasses already imported into the process via __subclasses__().

    Can be used standalone or called from ServiceSupervisorAgent.

    Args:
        model: Any MindtraceAgent-compatible LLM model.
        roots: Package namespaces to scan (default: ["mindtrace.services"]).
               Add your own package here to include custom services.
        extra_tools: Additional Tool objects to attach.
    """

    def __init__(
        self,
        model: Any,
        roots: list[str] | None = None,
        extra_tools: Optional[Sequence[Any]] = None,
    ) -> None:
        from mindtrace.agents.core.base import MindtraceAgent
        from mindtrace.agents.tools._tool import Tool

        self._catalog = scan_services(roots)
        logger.info(
            "ServiceLauncherAgent ready — %d service(s) in catalog.",
            len(self._catalog),
        )

        self._deps = LauncherDeps(catalog=self._catalog)
        self._message_history: list = []

        tools = [
            Tool(list_available_services),
            Tool(start_service),
            *list(extra_tools or []),
        ]

        self._agent = MindtraceAgent(
            model=model,
            tools=tools,
            system_prompt=_LAUNCHER_PROMPT,
            _name="service_launcher",
        )

    async def run(self, query: str, **kwargs: Any) -> str:
        return await self._agent.run(
            query,
            deps=self._deps,
            message_history=self._message_history,
            **kwargs,
        )

    def run_sync(self, query: str, **kwargs: Any) -> str:
        return self._agent.run_sync(
            query,
            deps=self._deps,
            message_history=self._message_history,
            **kwargs,
        )

    def clear_history(self) -> None:
        self._message_history.clear()

    @property
    def catalog(self) -> dict[str, CatalogEntry]:
        return self._catalog
