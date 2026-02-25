"""Topology: describes the physical layout of a compute cluster.

Provides factory methods for common deployment shapes (local single-process,
local multi-GPU, multi-host) and produces the environment-variable dictionary
required by :mod:`torch.distributed` for ``env://`` initialisation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from mindtrace.cluster.node import ClusterNode, NodeInfo, NodeStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional torch dependency
# ---------------------------------------------------------------------------
try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


class TopologyType(str, Enum):
    """Classification of the cluster's physical layout."""

    LOCAL = "local"
    LOCAL_MULTI_GPU = "local_multi_gpu"
    MULTI_HOST = "multi_host"


@dataclass
class Topology:
    """Describes the physical layout of the cluster.

    Attributes:
        topology_type: The broad category of the deployment shape.
        nodes: Ordered list of :class:`NodeInfo` snapshots describing each
            participating process/host.
        world_size: Total number of participating processes (ranks).
        master_host: Hostname or IP address of rank-0 — used by
            :mod:`torch.distributed` for rendezvous.
        master_port: TCP port on which rank-0 listens for peer connections.
    """

    topology_type: TopologyType
    nodes: list[NodeInfo]
    world_size: int
    master_host: str = "localhost"
    master_port: int = 29500

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def local(cls, num_gpus: int | None = None) -> "Topology":
        """Build a topology for a single-machine deployment.

        Auto-detects the number of available CUDA devices when *num_gpus* is
        ``None`` and :mod:`torch` is importable.  Falls back to a single
        CPU-only process when no GPUs are detected or torch is unavailable.

        Args:
            num_gpus: Explicit GPU count override.  Pass ``0`` to force a
                CPU-only topology even when GPUs are present.

        Returns:
            A :class:`Topology` instance configured for the local machine.
        """
        if num_gpus is None:
            if _TORCH_AVAILABLE:
                num_gpus = torch.cuda.device_count()
                logger.debug("Auto-detected %d CUDA devices", num_gpus)
            else:
                num_gpus = 0
                logger.debug("torch not available — defaulting to CPU-only topology")

        if num_gpus <= 1:
            topo_type = TopologyType.LOCAL
            gpus = list(range(num_gpus))
            node_info = NodeInfo(
                node_id="local-0",
                host="localhost",
                port=29500,
                gpus=gpus,
                status=NodeStatus.IDLE,
                current_job=None,
            )
            return cls(
                topology_type=topo_type,
                nodes=[node_info],
                world_size=1,
                master_host="localhost",
                master_port=29500,
            )

        topo_type = TopologyType.LOCAL_MULTI_GPU
        nodes = [
            NodeInfo(
                node_id=f"local-{i}",
                host="localhost",
                port=29500 + i,
                gpus=[i],
                status=NodeStatus.IDLE,
                current_job=None,
            )
            for i in range(num_gpus)
        ]
        return cls(
            topology_type=topo_type,
            nodes=nodes,
            world_size=num_gpus,
            master_host="localhost",
            master_port=29500,
        )

    @classmethod
    def from_nodes(cls, nodes: list[ClusterNode]) -> "Topology":
        """Build a topology from an existing list of :class:`ClusterNode` objects.

        The first node in *nodes* is treated as the master for distributed
        rendezvous.  The ``world_size`` equals ``len(nodes)``.

        Args:
            nodes: Ordered list of cluster nodes.  Must contain at least one
                node.

        Returns:
            A :class:`Topology` reflecting the provided node list.

        Raises:
            ValueError: If *nodes* is empty.
        """
        if not nodes:
            raise ValueError("Cannot build a Topology from an empty node list.")

        infos = [n.to_info() for n in nodes]
        master = infos[0]

        if len(nodes) == 1:
            if infos[0].gpus:
                topo_type = TopologyType.LOCAL_MULTI_GPU if len(infos[0].gpus) > 1 else TopologyType.LOCAL
            else:
                topo_type = TopologyType.LOCAL
        else:
            all_local = all(info.host in ("localhost", "127.0.0.1") for info in infos)
            topo_type = TopologyType.LOCAL_MULTI_GPU if all_local else TopologyType.MULTI_HOST

        return cls(
            topology_type=topo_type,
            nodes=infos,
            world_size=len(nodes),
            master_host=master.host,
            master_port=master.port,
        )

    # ------------------------------------------------------------------
    # Environment variable export
    # ------------------------------------------------------------------

    def to_env(self) -> dict[str, str]:
        """Return environment variables suitable for :mod:`torch.distributed` init.

        The returned dictionary contains:

        - ``MASTER_ADDR``: hostname/IP of rank-0.
        - ``MASTER_PORT``: port of rank-0 as a string.
        - ``WORLD_SIZE``: total number of ranks as a string.

        These variables are consumed by ``torch.distributed.init_process_group``
        when ``init_method="env://"``.

        Returns:
            A dict of environment variable name to string value.
        """
        return {
            "MASTER_ADDR": self.master_host,
            "MASTER_PORT": str(self.master_port),
            "WORLD_SIZE": str(self.world_size),
        }

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Topology(type={self.topology_type.value!r}, "
            f"world_size={self.world_size}, "
            f"master={self.master_host}:{self.master_port})"
        )

    def __len__(self) -> int:
        """Return the number of nodes (ranks) in the topology."""
        return self.world_size
