import time

import pytest

from mindtrace.cluster import ClusterManager, Node


def wait_for_job_status(cluster_cm, job_id, expected_status, timeout=10, poll_interval=0.1):
    """Poll job status until it matches expected_status or timeout."""
    start = time.time()
    result = None
    while time.time() - start < timeout:
        result = cluster_cm.get_job_status(job_id=job_id)
        if result.status == expected_status:
            return result
        time.sleep(poll_interval)
    pytest.fail(f"Job {job_id} did not reach '{expected_status}' within {timeout}s. Last: {result.status}")


@pytest.fixture(scope="module")
def _shared_cluster_cm():
    """Module-scoped ClusterManager — launched once, reused across all tests in a file."""
    cm = ClusterManager.launch(host="localhost", port=8080, wait_for_launch=True, timeout=30)
    try:
        yield cm
    finally:
        cm.clear_databases()
        cm.shutdown()


@pytest.fixture
def cluster_cm(_shared_cluster_cm):
    """Function-scoped wrapper that clears databases before each test for isolation."""
    _shared_cluster_cm.clear_databases()
    return _shared_cluster_cm


@pytest.fixture(scope="module")
def _shared_node(_shared_cluster_cm):
    """Module-scoped Node — launched once, connected to the shared ClusterManager."""
    n = Node.launch(
        host="localhost",
        port=8081,
        cluster_url=str(_shared_cluster_cm.url),
        wait_for_launch=True,
        timeout=30,
    )
    try:
        yield n
    finally:
        n.shutdown()


@pytest.fixture
def node(cluster_cm, _shared_node):
    """Function-scoped wrapper. Cleans up workers and depends on cluster_cm for DB cleanup ordering."""
    _shared_node.shutdown_all_workers()
    return _shared_node
