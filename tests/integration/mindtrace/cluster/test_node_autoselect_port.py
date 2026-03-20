import pytest
from fastapi.exceptions import HTTPException

from mindtrace.cluster import Worker


@pytest.mark.integration
def test_node_launch_worker_autoselect_port(cluster_cm, node):
    """Integration test for Node.launch_worker with auto-select port."""
    cluster_cm.register_worker_type(
        worker_name="echoworker",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="auto_connect_db_echo",
    )

    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker0"
    )
    assert output.worker_url == "http://localhost:8200"
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker1"
    )
    assert output.worker_url == "http://localhost:8201"
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker2"
    )
    assert output.worker_url == "http://localhost:8202"
    with pytest.raises(HTTPException):
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker3"
        )


@pytest.mark.integration
def test_node_launch_worker_autoselect_port_reuse_port(cluster_cm, node):
    """Integration test for Node.launch_worker with auto-select port and reuse port."""
    cluster_cm.register_worker_type(
        worker_name="echoworker",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="auto_connect_db_echo",
    )

    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker0"
    )
    assert output.worker_url == "http://localhost:8200"
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker1"
    )
    assert output.worker_url == "http://localhost:8201"
    node.shutdown_all_workers()
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker2"
    )
    assert output.worker_url == "http://localhost:8200"
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker3"
    )
    assert output.worker_url == "http://localhost:8201"


@pytest.mark.integration
def test_node_launch_worker_autoselect_port_worker_crashed(cluster_cm, node):
    """Integration test for Node.launch_worker with auto-select port."""
    cluster_cm.register_worker_type(
        worker_name="echoworker",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="auto_connect_db_echo",
    )

    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker0"
    )
    assert output.worker_url == "http://localhost:8200"
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker1"
    )
    assert output.worker_url == "http://localhost:8201"
    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker2"
    )
    assert output.worker_url == "http://localhost:8202"

    worker_cm = Worker.connect(url="http://localhost:8201")
    worker_cm.shutdown()

    output = cluster_cm.launch_worker(
        node_url=str(node.url), worker_type="echoworker", worker_url=None, worker_name="echoworker3"
    )
    assert output.worker_url == "http://localhost:8201"
