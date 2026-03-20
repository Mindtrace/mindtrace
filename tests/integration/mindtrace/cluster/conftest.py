import time

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


@pytest.fixture
def cluster_cm():
    """Function-scoped ClusterManager with dynamic port."""
    port = get_free_port()
    cm = ClusterManager.launch(host="localhost", port=port, wait_for_launch=True, timeout=30)
    try:
        cm.clear_databases()
        yield cm
    finally:
        cm.clear_databases()
        cm.shutdown()


@pytest.fixture
def node(cluster_cm):
    """Function-scoped Node connected to the test's ClusterManager."""
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
