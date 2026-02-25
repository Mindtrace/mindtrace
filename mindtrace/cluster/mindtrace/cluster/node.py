"""ClusterNode: represents one compute worker node in a cluster.

Maintains node metadata, health-check pinging, and GPU availability tracking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import requests

from mindtrace.core import Mindtrace


class NodeStatus(str, Enum):
    """Operational status of a cluster node."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class NodeInfo:
    """Serialisable snapshot of a ClusterNode's current state."""

    node_id: str
    host: str
    port: int
    gpus: list[int]
    status: NodeStatus
    current_job: str | None


class ClusterNode(Mindtrace):
    """Represents a single compute node in the cluster.

    Maintains node metadata, health-check pinging, and GPU availability.
    A node exposes a ``/health`` HTTP endpoint that returns HTTP 200 when the
    process is reachable.  GPU indices are supplied at construction time and
    are used to report capacity to the manager.

    Args:
        node_id: Unique identifier for this node.
        host: Hostname or IP address of the node.
        port: HTTP port on which the node's service is listening.
        gpus: List of integer GPU device indices available on this node.
            Defaults to an empty list (CPU-only node).
        ping_timeout: Seconds before the health-check HTTP request times out.
    """

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        gpus: list[int] | None = None,
        ping_timeout: float = 5.0,
    ) -> None:
        super().__init__()
        self.node_id = node_id
        self.host = host
        self.port = port
        self.gpus: list[int] = gpus if gpus is not None else []
        self.ping_timeout = ping_timeout
        self._status: NodeStatus = NodeStatus.IDLE
        self._current_job: str | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Send an HTTP GET request to the node's ``/health`` endpoint.

        Returns:
            ``True`` when the node replies with HTTP 2xx, ``False`` otherwise
            (connection error, timeout, or non-2xx status code).
        """
        url = f"http://{self.host}:{self.port}/health"
        try:
            response = requests.get(url, timeout=self.ping_timeout)
            reachable = response.status_code < 300
            if not reachable:
                self.logger.warning(
                    "Node %s health check returned HTTP %s",
                    self.node_id,
                    response.status_code,
                )
            return reachable
        except requests.exceptions.RequestException as exc:
            self.logger.debug("Node %s unreachable: %s", self.node_id, exc)
            return False

    def gpu_count(self) -> int:
        """Return the number of GPU devices registered on this node."""
        return len(self.gpus)

    def is_available(self) -> bool:
        """Return ``True`` when the node is IDLE and responds to a health ping.

        A node is considered available for new work only when both conditions
        are satisfied: its recorded status is ``IDLE`` and a live ping
        succeeds.
        """
        if self._status != NodeStatus.IDLE:
            return False
        return self.ping()

    def to_info(self) -> NodeInfo:
        """Build and return a serialisable :class:`NodeInfo` snapshot."""
        return NodeInfo(
            node_id=self.node_id,
            host=self.host,
            port=self.port,
            gpus=list(self.gpus),
            status=self._status,
            current_job=self._current_job,
        )

    # ------------------------------------------------------------------
    # Status management helpers (used by ClusterManager)
    # ------------------------------------------------------------------

    @property
    def status(self) -> NodeStatus:
        """Current operational status of this node."""
        return self._status

    @status.setter
    def status(self, value: NodeStatus) -> None:
        self._status = value

    @property
    def current_job(self) -> str | None:
        """Job ID currently running on this node, or ``None`` when idle."""
        return self._current_job

    @current_job.setter
    def current_job(self, job_id: str | None) -> None:
        self._current_job = job_id

    def mark_busy(self, job_id: str) -> None:
        """Transition node status to BUSY and record the running job ID."""
        self._status = NodeStatus.BUSY
        self._current_job = job_id
        self.logger.debug("Node %s marked BUSY for job %s", self.node_id, job_id)

    def mark_idle(self) -> None:
        """Transition node status to IDLE and clear the current job."""
        self._status = NodeStatus.IDLE
        self._current_job = None
        self.logger.debug("Node %s marked IDLE", self.node_id)

    def mark_offline(self) -> None:
        """Transition node status to OFFLINE."""
        self._status = NodeStatus.OFFLINE
        self.logger.info("Node %s marked OFFLINE", self.node_id)

    def mark_error(self) -> None:
        """Transition node status to ERROR."""
        self._status = NodeStatus.ERROR
        self.logger.warning("Node %s marked ERROR", self.node_id)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ClusterNode(node_id={self.node_id!r}, "
            f"host={self.host!r}, port={self.port}, "
            f"gpus={self.gpus!r}, status={self._status.value!r})"
        )
