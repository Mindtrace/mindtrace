"""ClusterManager: orchestrates a pool of ClusterNodes, dispatches work.

Supports round-robin and least-loaded dispatch strategies, fan-out map
operations, and real-time node status reporting.  This manager is the
lightweight, callable-dispatch counterpart to the HTTP-service-based
``mindtrace.cluster.core.cluster.ClusterManager``.
"""
from __future__ import annotations

import asyncio
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from mindtrace.core import Mindtrace

from mindtrace.cluster.node import ClusterNode, NodeInfo, NodeStatus
from mindtrace.cluster.worker import Worker, WorkerResult


class ClusterManager(Mindtrace):
    """Orchestrates a pool of :class:`ClusterNode` instances, dispatches work.

    Supports two dispatch strategies:

    - ``"round_robin"``: cycles through nodes in insertion order, skipping
      any that are not available.
    - ``"least_loaded"`` (default): picks the node with the fewest BUSY
      assignments (falls back to any IDLE node that responds to a ping).

    The manager is thread-safe: :meth:`dispatch` and :meth:`map` acquire a
    lock before selecting a node so that concurrent callers do not race on
    node availability.

    Args:
        nodes: Initial list of :class:`ClusterNode` instances.  Nodes may
            also be added later with :meth:`add_node`.
        strategy: Dispatch strategy — ``"round_robin"`` or
            ``"least_loaded"``.
        registry: Optional :class:`mindtrace.registry.Registry` instance for
            persisting node metadata.  Not used internally at this time but
            accepted for API symmetry with the rest of the ecosystem.
    """

    def __init__(
        self,
        nodes: list[ClusterNode] | None = None,
        strategy: str = "least_loaded",
        registry: Any | None = None,
    ) -> None:
        super().__init__()
        self._nodes: dict[str, ClusterNode] = {}
        self._lock = threading.Lock()
        self._round_robin_iter: itertools.cycle | None = None
        self.strategy = strategy
        self.registry = registry

        for node in (nodes or []):
            self.add_node(node)

        if strategy not in ("round_robin", "least_loaded"):
            raise ValueError(
                f"Unknown dispatch strategy {strategy!r}. "
                "Expected 'round_robin' or 'least_loaded'."
            )

    # ------------------------------------------------------------------
    # Node registry management
    # ------------------------------------------------------------------

    def add_node(self, node: ClusterNode) -> None:
        """Register a new node with the manager.

        Args:
            node: The :class:`ClusterNode` to add.

        Raises:
            ValueError: If a node with the same ``node_id`` is already
                registered.
        """
        with self._lock:
            if node.node_id in self._nodes:
                raise ValueError(
                    f"Node {node.node_id!r} is already registered. "
                    "Use remove_node() first to replace it."
                )
            self._nodes[node.node_id] = node
            self._rebuild_round_robin()
            self.logger.info("Registered node %s (%s:%s)", node.node_id, node.host, node.port)

    def remove_node(self, node_id: str) -> None:
        """Deregister a node by its identifier.

        Args:
            node_id: Identifier of the node to remove.

        Raises:
            KeyError: If no node with *node_id* is registered.
        """
        with self._lock:
            if node_id not in self._nodes:
                raise KeyError(f"No node with id {node_id!r} is registered.")
            del self._nodes[node_id]
            self._rebuild_round_robin()
            self.logger.info("Removed node %s", node_id)

    # ------------------------------------------------------------------
    # Dispatch — synchronous
    # ------------------------------------------------------------------

    def dispatch(self, fn: Callable, *args: Any, **kwargs: Any) -> WorkerResult:
        """Pick an available node and run *fn* on it synchronously.

        Args:
            fn: The callable to execute.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.  The special
                keyword ``timeout`` (float | None) is extracted and passed to
                :meth:`Worker.run` rather than to *fn*.

        Returns:
            A :class:`WorkerResult` from the executing worker.

        Raises:
            RuntimeError: If no available nodes exist in the pool.
        """
        timeout = kwargs.pop("timeout", None)
        node = self._select_node()
        worker = Worker(node=node, device=self._pick_device(node))
        self.logger.debug(
            "Dispatching %s to node %s",
            getattr(fn, "__name__", repr(fn)),
            node.node_id,
        )
        result = worker.run(fn, *args, timeout=timeout, **kwargs)
        return result

    # ------------------------------------------------------------------
    # Dispatch — asynchronous
    # ------------------------------------------------------------------

    async def dispatch_async(self, fn: Callable, *args: Any, **kwargs: Any) -> WorkerResult:
        """Pick an available node and run *fn* on it asynchronously.

        Args:
            fn: The callable to execute.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.  The special
                keyword ``timeout`` (float | None) is extracted and passed to
                :meth:`Worker.run_async` rather than to *fn*.

        Returns:
            A :class:`WorkerResult` from the executing worker.

        Raises:
            RuntimeError: If no available nodes exist in the pool.
        """
        timeout = kwargs.pop("timeout", None)
        node = self._select_node()
        worker = Worker(node=node, device=self._pick_device(node))
        self.logger.debug(
            "Async-dispatching %s to node %s",
            getattr(fn, "__name__", repr(fn)),
            node.node_id,
        )
        result = await worker.run_async(fn, *args, timeout=timeout, **kwargs)
        return result

    # ------------------------------------------------------------------
    # Map — parallel fan-out
    # ------------------------------------------------------------------

    def map(
        self,
        fn: Callable,
        items: list[Any],
        **kwargs: Any,
    ) -> list[WorkerResult]:
        """Fan out ``fn(item)`` across available nodes in parallel.

        Each *item* in *items* is submitted as a separate task.  Tasks are
        distributed to available nodes concurrently using a thread pool.
        The results list preserves the original order of *items*.

        Args:
            fn: The callable to apply to each item.
            items: The list of arguments to map over.
            **kwargs: Keyword arguments forwarded to every call of *fn*.
                The special keyword ``timeout`` is forwarded to each
                :class:`Worker` invocation.

        Returns:
            A list of :class:`WorkerResult` in the same order as *items*.
        """
        timeout = kwargs.pop("timeout", None)
        results: list[WorkerResult | None] = [None] * len(items)

        def _run_one(index: int, item: Any) -> tuple[int, WorkerResult]:
            node = self._select_node()
            worker = Worker(node=node, device=self._pick_device(node))
            return index, worker.run(fn, item, timeout=timeout, **kwargs)

        max_workers = max(1, len(self._nodes))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_one, idx, item): idx
                for idx, item in enumerate(items)
            }
            for future in as_completed(futures):
                idx, result = future.result()
                results[idx] = result

        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Status and introspection
    # ------------------------------------------------------------------

    def status(self) -> dict[str, NodeInfo]:
        """Return a snapshot of all registered nodes' current status.

        Returns:
            A mapping of ``node_id`` to :class:`NodeInfo`.
        """
        with self._lock:
            return {nid: node.to_info() for nid, node in self._nodes.items()}

    def available_nodes(self) -> list[ClusterNode]:
        """Return all nodes that are currently available for new work.

        A node is considered available when :meth:`ClusterNode.is_available`
        returns ``True`` (IDLE status and successful health ping).
        """
        with self._lock:
            return [node for node in self._nodes.values() if node.is_available()]

    def gpu_total(self) -> int:
        """Return the total number of GPU devices across all registered nodes."""
        with self._lock:
            return sum(node.gpu_count() for node in self._nodes.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_node(self) -> ClusterNode:
        """Select a node according to the configured dispatch strategy.

        Raises:
            RuntimeError: If no available nodes can be found.
        """
        with self._lock:
            if not self._nodes:
                raise RuntimeError("No nodes registered with ClusterManager.")

            if self.strategy == "round_robin":
                return self._select_round_robin()
            return self._select_least_loaded()

    def _select_round_robin(self) -> ClusterNode:
        """Cycle through nodes in order, returning the first available one."""
        if self._round_robin_iter is None:
            raise RuntimeError("No nodes registered with ClusterManager.")

        node_ids = list(self._nodes.keys())
        attempts = 0
        while attempts < len(node_ids):
            node_id = next(self._round_robin_iter)
            node = self._nodes.get(node_id)
            if node is not None and node.is_available():
                return node
            attempts += 1

        raise RuntimeError(
            "No available nodes found (round_robin). "
            f"Registered nodes: {list(self._nodes.keys())}"
        )

    def _select_least_loaded(self) -> ClusterNode:
        """Return the IDLE node that is least loaded (fewest BUSY assignments).

        When all nodes are BUSY, falls back to whichever IDLE node responds
        to a ping first in iteration order.
        """
        idle_nodes = [
            node for node in self._nodes.values()
            if node.status == NodeStatus.IDLE
        ]
        if not idle_nodes:
            raise RuntimeError(
                "No IDLE nodes available (least_loaded). "
                f"Registered nodes: {list(self._nodes.keys())}"
            )

        # Among idle nodes, prefer those that pass the live ping check.
        available = [n for n in idle_nodes if n.ping()]
        candidates = available if available else idle_nodes

        # Sort by gpu_count descending (prefer nodes with more compute) as a
        # secondary heuristic; primary is IDLE status verified above.
        candidates.sort(key=lambda n: n.gpu_count(), reverse=True)
        return candidates[0]

    def _pick_device(self, node: ClusterNode) -> str:
        """Return a device string for a node.

        If the node has GPUs, returns ``"cuda:<first_gpu_index>"``.
        Otherwise returns ``"cpu"``.
        """
        if node.gpus:
            return f"cuda:{node.gpus[0]}"
        return "cpu"

    def _rebuild_round_robin(self) -> None:
        """Rebuild the round-robin iterator from the current node set."""
        self._round_robin_iter = itertools.cycle(list(self._nodes.keys()))

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ClusterManager(nodes={list(self._nodes.keys())!r}, "
            f"strategy={self.strategy!r})"
        )

    def __len__(self) -> int:
        return len(self._nodes)
