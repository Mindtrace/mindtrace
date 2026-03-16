import time

import os

import pytest

from mindtrace.cluster import ClusterManager, Node
from mindtrace.core import get_free_port


def wait_for_job_status(cm, job_id, expected_status, timeout=10, poll_interval=0.1):
    """Poll job status until it matches expected_status or timeout."""
    start = time.time()
    result = None
    while time.time() - start < timeout:
        result = cm.get_job_status(job_id=job_id)
        if result.status == expected_status:
            return result
        time.sleep(poll_interval)
    pytest.fail(f"Job {job_id} did not reach '{expected_status}' within {timeout}s. Last: {result.status}")


@pytest.fixture(scope="session")
def cluster_cm():
    """Session-scoped ClusterManager with dynamic port."""
    port = get_free_port()
    cm = ClusterManager.launch(host="localhost", port=port, wait_for_launch=True, timeout=30)
    try:
        cm.clear_databases()
        yield cm
    finally:
        cm.clear_databases()
        cm.shutdown()


@pytest.fixture(scope="session")
def node(cluster_cm):
    """Session-scoped Node connected to the test's ClusterManager."""
    # Use a non-default worker ports range to avoid conflicts with services
    # that might already be listening on the default 8200-8202 range.
    os.environ["MINDTRACE_CLUSTER__WORKER_PORTS_RANGE"] = "8300-8302"
    port = get_free_port()
    n = Node.launch(
        host="localhost",
        port=port,
        cluster_url=str(cluster_cm.url),
        wait_for_launch=True,
        timeout=30,
    )
    try:
        yield n
    finally:
        n.shutdown_all_workers()
        n.shutdown()


@pytest.fixture(autouse=True)
def _reset_cluster_state(request, cluster_cm):
    """Reset cluster state between tests."""
    yield
    cluster_cm.clear_databases()
    if "node" in request.fixturenames:
        node = request.getfixturevalue("node")
        node.shutdown_all_workers()
