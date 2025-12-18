import pytest
from fastapi.exceptions import HTTPException

from mindtrace.cluster import ClusterManager, Node, Worker


@pytest.mark.integration
def test_node_launch_worker_autoselect_port():
    """Integration test for Node.launch_worker with auto-select port."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8155, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8156, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
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

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_node_launch_worker_autoselect_port_reuse_port():
    """Integration test for Node.launch_worker with auto-select port and reuse port."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8155, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8156, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
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

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_node_launch_worker_autoselect_port_worker_crashed():
    """Integration test for Node.launch_worker with auto-select port."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8155, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8156, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
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

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()
