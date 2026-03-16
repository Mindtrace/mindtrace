import pytest

from mindtrace.cluster import Worker
from mindtrace.cluster.core.types import LaunchStatusEnum

from .conftest import wait_for_worker_launch


@pytest.mark.integration
def test_node_launch_worker_autoselect_port(cluster_cm, node):
    """Integration test for Node.launch_worker with auto-select port."""
    cluster_cm.register_worker_type(
        worker_name="echoworker",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="auto_connect_db_echo",
    )

    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker0"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8300"
    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker1"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8301"
    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker2"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8302"
    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker3"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.FAILED


@pytest.mark.integration
def test_node_launch_worker_autoselect_port_reuse_port(cluster_cm, node):
    """Integration test for Node.launch_worker with auto-select port and reuse port."""
    cluster_cm.register_worker_type(
        worker_name="echoworker",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="auto_connect_db_echo",
    )

    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker0"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8300"

    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker1"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8301"
    node.shutdown_all_workers()

    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker2"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8300"
    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker3"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8301"


@pytest.mark.integration
def test_node_launch_worker_autoselect_port_worker_crashed(cluster_cm, node):
    """Integration test for Node.launch_worker with auto-select port."""
    cluster_cm.register_worker_type(
        worker_name="echoworker",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="auto_connect_db_echo",
    )

    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker0"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8300"
    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker1"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8301"
    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker2"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8302"

    worker_cm = Worker.connect(url="http://localhost:8301")
    worker_cm.shutdown()

    launch = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker3"
    )
    launch_status = wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)
    assert launch_status.status == LaunchStatusEnum.READY
    assert launch_status.worker_url == "http://localhost:8301"
