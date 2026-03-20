"""Worker: executes a callable task on a specific node/device.

Wraps synchronous and asynchronous task execution with timing, error capture,
and structured result reporting.  This module is intentionally distinct from
the service-oriented ``mindtrace.cluster.core.cluster.Worker`` class, which
inherits from :class:`mindtrace.services.Service` and communicates over HTTP.
The :class:`Worker` class here is a lightweight, dependency-free executor that
runs callables in-process, suitable for local and distributed scheduling.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

from mindtrace.cluster.node import ClusterNode
from mindtrace.core import Mindtrace


@dataclass
class WorkerResult:
    """Structured outcome of a single task execution.

    Attributes:
        success: ``True`` when the callable completed without raising an
            exception.
        result: The value returned by the callable, or ``None`` on failure.
        error: Human-readable error description, or ``None`` on success.
        elapsed_s: Wall-clock seconds consumed by the callable.
        node_id: Identifier of the :class:`ClusterNode` that hosted the run.
        device: Compute device string used (e.g. ``"cpu"``, ``"cuda:0"``).
    """

    success: bool
    result: Any
    error: str | None
    elapsed_s: float
    node_id: str
    device: str


class Worker(Mindtrace):
    """Executes a callable task on a specific node/device.

    Wraps task execution with timing, error capture, and result reporting.
    Both synchronous (:meth:`run`) and asynchronous (:meth:`run_async`)
    interfaces are provided.  Tasks that raise an exception are caught and
    surfaced through the :attr:`WorkerResult.error` field rather than
    propagated, so the manager can always receive a structured response.

    Args:
        node: The :class:`ClusterNode` on which this worker is resident.
        device: Compute device string (e.g. ``"cpu"``, ``"cuda:0"``).
            Passed through to :class:`WorkerResult` for observability; the
            caller is responsible for ensuring the callable actually uses the
            indicated device.
    """

    def __init__(self, node: ClusterNode, device: str = "cpu") -> None:
        super().__init__()
        self.node = node
        self.device = device

    # ------------------------------------------------------------------
    # Synchronous execution
    # ------------------------------------------------------------------

    def run(
        self,
        fn: Callable,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> WorkerResult:
        """Execute *fn* synchronously and return a :class:`WorkerResult`.

        The callable is invoked with ``fn(*args, **kwargs)``.  If *timeout* is
        provided and the call takes longer, a :exc:`TimeoutError` is raised
        inside the worker and captured in the result's ``error`` field.

        Args:
            fn: The callable to execute.
            *args: Positional arguments forwarded to *fn*.
            timeout: Maximum allowed wall-clock seconds.  ``None`` means no
                limit.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            A :class:`WorkerResult` describing the outcome.
        """
        self.logger.debug(
            "Worker on node %s starting %s (device=%s, timeout=%s)",
            self.node.node_id,
            getattr(fn, "__name__", repr(fn)),
            self.device,
            timeout,
        )
        start = time.perf_counter()
        result_value: Any = None
        error_msg: str | None = None
        success = False

        try:
            if timeout is not None:
                result_value = self._run_with_timeout(fn, args, kwargs, timeout)
            else:
                result_value = fn(*args, **kwargs)
            success = True
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self.logger.error(
                "Worker on node %s failed executing %s: %s",
                self.node.node_id,
                getattr(fn, "__name__", repr(fn)),
                error_msg,
            )

        elapsed = time.perf_counter() - start
        return WorkerResult(
            success=success,
            result=result_value,
            error=error_msg,
            elapsed_s=elapsed,
            node_id=self.node.node_id,
            device=self.device,
        )

    # ------------------------------------------------------------------
    # Asynchronous execution
    # ------------------------------------------------------------------

    async def run_async(
        self,
        fn: Callable,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> WorkerResult:
        """Execute *fn* asynchronously and return a :class:`WorkerResult`.

        If *fn* is a coroutine function it is awaited directly; otherwise it
        is run in the default thread-pool executor via
        :func:`asyncio.get_event_loop().run_in_executor` so that blocking
        callables do not stall the event loop.

        Args:
            fn: The callable to execute.
            *args: Positional arguments forwarded to *fn*.
            timeout: Maximum allowed wall-clock seconds.  ``None`` means no
                limit.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            A :class:`WorkerResult` describing the outcome.
        """
        self.logger.debug(
            "Worker on node %s starting async %s (device=%s, timeout=%s)",
            self.node.node_id,
            getattr(fn, "__name__", repr(fn)),
            self.device,
            timeout,
        )
        start = time.perf_counter()
        result_value: Any = None
        error_msg: str | None = None
        success = False

        try:
            loop = asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(fn):
                coro = fn(*args, **kwargs)
            else:
                coro = loop.run_in_executor(None, lambda: fn(*args, **kwargs))

            if timeout is not None:
                result_value = await asyncio.wait_for(
                    coro if asyncio.iscoroutine(coro) else asyncio.ensure_future(coro),
                    timeout=timeout,
                )
            else:
                result_value = await coro
            success = True
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self.logger.error(
                "Worker on node %s failed async %s: %s",
                self.node.node_id,
                getattr(fn, "__name__", repr(fn)),
                error_msg,
            )

        elapsed = time.perf_counter() - start
        return WorkerResult(
            success=success,
            result=result_value,
            error=error_msg,
            elapsed_s=elapsed,
            node_id=self.node.node_id,
            device=self.device,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_with_timeout(
        self,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        timeout: float,
    ) -> Any:
        """Run *fn* in a thread and raise :exc:`TimeoutError` if it exceeds *timeout* seconds.

        Uses :mod:`concurrent.futures` so the host thread is not blocked
        during the wait, and the timeout is enforced via
        :meth:`~concurrent.futures.Future.result`.
        """
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout:
                raise TimeoutError(
                    f"Task {getattr(fn, '__name__', repr(fn))!r} exceeded "
                    f"{timeout}s timeout on node {self.node.node_id}"
                )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Worker(node_id={self.node.node_id!r}, device={self.device!r})"
