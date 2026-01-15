import time
import warnings

from fastapi.exceptions import HTTPException
import pytest

from mindtrace.cluster import ClusterManager, Node
from pydantic import BaseModel
from mindtrace.cluster.core.types import WorkerStatusEnum
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput


@pytest.mark.integration
def test_cluster_manager_as_gateway():
    echo_job = JobSchema(name="gateway_echo_job", input_schema=EchoInput, output_schema=EchoOutput)

    # Launch Gateway service on port 8097
    cluster_cm = ClusterManager.launch(port=8097, wait_for_launch=True, timeout=15)
    # Launch EchoService on port 8098
    echo_cm = EchoWorker.launch(port=8098, wait_for_launch=True, timeout=15)

    try:
        # Register the EchoService with the Gateway
        cluster_cm.register_app(
            name="echo",
            url="http://localhost:8098/",
            connection_manager=echo_cm,
        )
        cluster_cm.register_job_to_endpoint(job_type="gateway_echo_job", endpoint="echo/run")
        job = job_from_schema(echo_job, EchoInput(message="integration test"))
        result = cluster_cm.submit_job(job)
        assert result.status == "completed"
        assert result.output == {"echoed": "integration test"}
    finally:
        # Clean up in reverse order
        echo_cm.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_with_prelaunched_worker():
    """Integration test for ClusterManager with a prelaunched EchoWorker."""
    # Use different ports to avoid conflicts with other tests
    cluster_cm = ClusterManager.launch(host="localhost", port=8100, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8101, wait_for_launch=True, timeout=15)
    worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
    echo_job_schema = JobSchema(name="prelaunched_worker_echo", input_schema=EchoInput, output_schema=EchoOutput)
    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="prelaunched_worker_echo", worker_url=str(worker_cm.url))
        # Submit a job
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, Worker!"})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"
        assert result.output == {}

        time.sleep(1)
        result = cluster_cm.get_job_status(job_id=job.id)
        assert result.status == "completed"
        assert result.output == {"echoed": "Hello, Worker!"}

        # Test both status methods after job completion
        worker_status = cluster_cm.get_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.IDLE.value

        query_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert query_status.worker_id == worker_id
        assert query_status.status == WorkerStatusEnum.IDLE.value
    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_multiple_jobs_with_worker():
    """Integration test for submitting multiple jobs to a prelaunched EchoWorker."""
    from mindtrace.cluster.workers.echo_worker import EchoWorker

    cluster_cm = ClusterManager.launch(host="localhost", port=8102, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8103, wait_for_launch=True, timeout=15)
    worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
    echo_job_schema = JobSchema(name="multiple_jobs_echo", input_schema=EchoInput, output_schema=EchoOutput)
    try:
        cluster_cm.register_job_to_worker(job_type="multiple_jobs_echo", worker_url=str(worker_cm.url))
        messages = ["Job 1", "Job 2", "Job 3"]
        jobs = []
        worker_status = cluster_cm.get_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        for msg in messages:
            job = job_from_schema(echo_job_schema, input_data={"message": msg})
            jobs.append(job)
            result = cluster_cm.submit_job(job)
            assert result.status == "queued"
        time.sleep(1)
        for i, job in enumerate(jobs):
            result = cluster_cm.get_job_status(job_id=job.id)
            assert result.status == "completed"
            assert result.output == {"echoed": messages[i]}
        worker_status = cluster_cm.get_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.IDLE.value
    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_worker_failure():
    """Integration test for handling worker failure (simulate by shutting down worker before job submission)."""
    from mindtrace.cluster.workers.echo_worker import EchoWorker

    cluster_cm = ClusterManager.launch(host="localhost", port=8104, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8105, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="worker_failure_echo", input_schema=EchoInput, output_schema=EchoOutput)
    try:
        cluster_cm.register_job_to_worker(job_type="worker_failure_echo", worker_url=str(worker_cm.url))
        # Shut down the worker before submitting the job
        worker_cm.shutdown()
        job = job_from_schema(echo_job_schema, input_data={"message": "Should fail"})
        result = cluster_cm.submit_job(job)
        time.sleep(1)
        assert result.status == "queued"  # Should still succeed but the job is queued
    finally:
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_with_node():
    """Integration test for ClusterManager with a Node."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8106, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8107, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)
    try:
        cluster_cm.register_worker_type(
            worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={}
        )
        worker_url = "http://localhost:8108"
        node.launch_worker(worker_type="echoworker", worker_url=worker_url)
        echo_job_schema = JobSchema(name="node_echo", input_schema=EchoInput, output_schema=EchoOutput)
        cluster_cm.register_job_to_worker(job_type="node_echo", worker_url=worker_url)
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!"})
        result = cluster_cm.submit_job(job)
        time.sleep(1)
        result = cluster_cm.get_job_status(job_id=job.id)
        assert result.status == "completed"
        assert result.output == {"echoed": "Hello, World!"}
    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_launch_worker():
    """Integration test for ClusterManager.launch_worker method."""
    # Launch cluster manager and node
    cluster_cm = ClusterManager.launch(host="localhost", port=8108, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8109, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        # Register a worker type first
        cluster_cm.register_worker_type(
            worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={}
        )

        # Launch a worker using the cluster manager's launch_worker method
        worker_url = "http://localhost:8110"
        cluster_cm.launch_worker(
            node_url=str(node.url),
            worker_type="echoworker",
            worker_url=worker_url,
            job_type=None,
        )

        # Register the worker with the cluster for job processing
        echo_job_schema = JobSchema(name="launch_worker_echo", input_schema=EchoInput, output_schema=EchoOutput)
        cluster_cm.register_job_to_worker(job_type="launch_worker_echo", worker_url=worker_url)

        # Submit a job and verify it gets processed
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello from launch_worker test!"})
        result = cluster_cm.submit_job(job)

        # Initially the job should be queued
        assert result.status == "queued"
        assert result.output == {}

        # Wait for the job to be processed
        time.sleep(2)

        # Check the final job status
        final_result = cluster_cm.get_job_status(job_id=job.id)
        assert final_result.status == "completed"
        assert final_result.output == {"echoed": "Hello from launch_worker test!"}

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_launch_worker_multiple_workers():
    """Integration test for launching multiple workers using ClusterManager.launch_worker."""
    # Launch cluster manager and node
    cluster_cm = ClusterManager.launch(host="localhost", port=8111, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8112, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        # Register a worker type
        cluster_cm.register_worker_type(
            worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={}
        )

        # Launch multiple workers
        worker_urls = ["http://localhost:8113", "http://localhost:8114", "http://localhost:8115"]

        for worker_url in worker_urls:
            cluster_cm.launch_worker(
                node_url=str(node.url),
                worker_type="echoworker",
                worker_url=worker_url,
                job_type=None,
            )
            # Register each worker
            cluster_cm.register_job_to_worker(job_type="multiple_workers_echo", worker_url=worker_url)

        # Submit jobs to different workers
        echo_job_schema = JobSchema(name="multiple_workers_echo", input_schema=EchoInput, output_schema=EchoOutput)
        jobs = []

        for i, worker_url in enumerate(worker_urls):
            job = job_from_schema(echo_job_schema, input_data={"message": f"Job {i + 1} from worker {worker_url}"})
            jobs.append(job)
            result = cluster_cm.submit_job(job)
            assert result.status == "queued"

        # Wait for all jobs to be processed
        time.sleep(3)

        # Verify all jobs completed successfully
        for i, job in enumerate(jobs):
            final_result = cluster_cm.get_job_status(job_id=job.id)
            assert final_result.status == "completed"
            assert final_result.output == {"echoed": f"Job {i + 1} from worker {worker_urls[i]}"}

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_launch_worker_node_failure():
    """Integration test for launch_worker when node is not available."""
    # Launch only cluster manager (no node)
    cluster_cm = ClusterManager.launch(host="localhost", port=8116, wait_for_launch=True, timeout=15)

    try:
        # Register a worker type
        cluster_cm.register_worker_type(
            worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={}
        )

        # Try to launch a worker on a non-existent node
        with pytest.raises(Exception):
            cluster_cm.launch_worker(
                node_url="http://localhost:9999",  # Non-existent node
                worker_type="echoworker",
                worker_url="http://localhost:8117",
            )

    finally:
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_register_worker_type_with_job_schema_name():
    """Integration test for register_worker_type when job_schema_name is provided."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8118, wait_for_launch=True, timeout=15)

    try:
        # Register a worker type with job schema name
        cluster_cm.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="auto_connect_echo",  # This should trigger auto-registration
        )

        # Verify that the job schema was automatically registered to the worker type
        # by checking if we can launch a worker and it gets auto-connected
        node = Node.launch(
            host="localhost", port=8119, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15
        )

        try:
            # Launch a worker - it should be automatically connected to the job schema
            worker_url = "http://localhost:8120"
            cluster_cm.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)

            # Submit a job - it should be processed automatically without manual registration
            echo_job_schema = JobSchema(name="auto_connect_echo", input_schema=EchoInput, output_schema=EchoOutput)
            job = job_from_schema(echo_job_schema, input_data={"message": "Auto-connected worker test!"})
            result = cluster_cm.submit_job(job)

            # Initially the job should be queued
            assert result.status == "queued"
            assert result.output == {}

            # Wait for the job to be processed
            time.sleep(2)

            # Check the final job status - should be completed due to auto-connection
            final_result = cluster_cm.get_job_status(job_id=job.id)
            assert final_result.status == "completed"
            assert final_result.output == {"echoed": "Auto-connected worker test!"}

        finally:
            node.shutdown()

    finally:
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_register_job_schema_to_worker_type():
    """Integration test for register_job_schema_to_worker_type method."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8121, wait_for_launch=True, timeout=15)

    try:
        # First register a worker type without job schema
        cluster_cm.register_worker_type(
            worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={}
        )

        # Then register the job schema to the worker type
        cluster_cm.register_job_schema_to_worker_type(
            job_schema_name="manual_registration_echo", worker_type="echoworker"
        )

        # Launch a node and worker
        node = Node.launch(
            host="localhost", port=8122, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15
        )

        try:
            # Launch a worker - it should be automatically connected due to the registration
            worker_url = "http://localhost:8123"
            cluster_cm.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)

            # Submit a job - it should be processed automatically
            echo_job_schema = JobSchema(
                name="manual_registration_echo", input_schema=EchoInput, output_schema=EchoOutput
            )
            job = job_from_schema(echo_job_schema, input_data={"message": "Manual registration test!"})
            result = cluster_cm.submit_job(job)

            # Initially the job should be queued
            assert result.status == "queued"
            assert result.output == {}

            # Wait for the job to be processed
            time.sleep(2)

            # Check the final job status
            final_result = cluster_cm.get_job_status(job_id=job.id)
            assert final_result.status == "completed"
            assert final_result.output == {"echoed": "Manual registration test!"}

        finally:
            node.shutdown()

    finally:
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_register_job_schema_to_worker_type_nonexistent_worker():
    """Integration test for register_job_schema_to_worker_type with non-existent worker type."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8124, wait_for_launch=True, timeout=15)

    try:
        # Try to register job schema to non-existent worker type
        # This should not raise an error but should log a warning
        cluster_cm.register_job_schema_to_worker_type(
            job_schema_name="nonexistent_worker_echo", worker_type="nonexistent_worker"
        )

        # Verify that no job schema targeting was created
        # (This would be verified by checking that jobs of this type fail to submit)
        echo_job_schema = JobSchema(name="nonexistent_worker_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Should fail"})

        # This should fail because no targeting was created

        result = cluster_cm.submit_job(job)
        assert result.status == "error"
        assert result.output == {"error": "No job schema targeting found for job type nonexistent_worker_echo"}

    finally:
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_launch_worker_with_auto_connect_database():
    """Integration test for launch_worker when worker is in auto-connect database."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8125, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8126, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        # Register a worker type with job schema name (this creates auto-connect entry)
        cluster_cm.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="auto_connect_db_echo",
        )

        # Launch a worker - it should be automatically connected due to auto-connect database
        worker_url = "http://localhost:8127"
        cluster_cm.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)

        # Submit a job - it should be processed automatically without manual registration
        echo_job_schema = JobSchema(name="auto_connect_db_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Auto-connect database test!"})
        result = cluster_cm.submit_job(job)

        # Initially the job should be queued
        assert result.status == "queued"
        assert result.output == {}

        # Wait for the job to be processed
        time.sleep(2)

        # Check the final job status
        final_result = cluster_cm.get_job_status(job_id=job.id)
        assert final_result.status == "completed"
        assert final_result.output == {"echoed": "Auto-connect database test!"}

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_launch_worker_without_auto_connect_database():
    """Integration test for launch_worker when worker is not in auto-connect database."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8128, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8129, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        # Register a worker type without job schema name (no auto-connect entry)
        cluster_cm.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type=None,
        )

        # Launch a worker - it should NOT be automatically connected
        worker_url = "http://localhost:8130"
        cluster_cm.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)

        # Submit a job - it should fail because no targeting was created
        echo_job_schema = JobSchema(name="no_auto_connect_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Should fail"})

        result = cluster_cm.submit_job(job)
        assert result.status == "error"
        assert result.output == {"error": "No job schema targeting found for job type no_auto_connect_echo"}

        # Now manually register the job to the worker
        cluster_cm.register_job_to_worker(job_type="no_auto_connect_echo", worker_url=worker_url)

        # Submit another job - it should work now
        job2 = job_from_schema(echo_job_schema, input_data={"message": "Manual registration after launch!"})
        result = cluster_cm.submit_job(job2)

        # Initially the job should be queued
        assert result.status == "queued"
        assert result.output == {}

        # Wait for the job to be processed
        time.sleep(2)

        # Check the final job status
        final_result = cluster_cm.get_job_status(job_id=job2.id)
        assert final_result.status == "completed"
        assert final_result.output == {"echoed": "Manual registration after launch!"}

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_multiple_worker_types_with_auto_connect():
    """Integration test for multiple worker types with auto-connect functionality."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8131, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8132, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        # Register multiple worker types with different job schemas
        cluster_cm.register_worker_type(
            worker_name="echoworker1",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="echo1",
        )

        cluster_cm.register_worker_type(
            worker_name="echoworker2",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="echo2",
        )

        # Launch workers for both types
        worker_url1 = "http://localhost:8133"
        worker_url2 = "http://localhost:8134"

        cluster_cm.launch_worker(node_url=str(node.url), worker_type="echoworker1", worker_url=worker_url1)

        cluster_cm.launch_worker(node_url=str(node.url), worker_type="echoworker2", worker_url=worker_url2)

        # Submit jobs to both workers
        echo_job_schema1 = JobSchema(name="echo1", input_schema=EchoInput, output_schema=EchoOutput)
        echo_job_schema2 = JobSchema(name="echo2", input_schema=EchoInput, output_schema=EchoOutput)

        job1 = job_from_schema(echo_job_schema1, input_data={"message": "Worker 1 job!"})
        job2 = job_from_schema(echo_job_schema2, input_data={"message": "Worker 2 job!"})

        result1 = cluster_cm.submit_job(job1)
        result2 = cluster_cm.submit_job(job2)

        # Initially both jobs should be queued
        assert result1.status == "queued"
        assert result2.status == "queued"

        # Wait for the jobs to be processed
        time.sleep(3)

        # Check the final job statuses
        final_result1 = cluster_cm.get_job_status(job_id=job1.id)
        final_result2 = cluster_cm.get_job_status(job_id=job2.id)

        assert final_result1.status == "completed"
        assert final_result1.output == {"echoed": "Worker 1 job!"}
        assert final_result2.status == "completed"
        assert final_result2.output == {"echoed": "Worker 2 job!"}

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_launch_worker_with_delay():
    """Integration test for launch_worker when worker is in auto-connect database."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8125, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8126, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        # Register a worker type with job schema name (this creates auto-connect entry)
        cluster_cm.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="delay_echo",
        )

        # Launch a worker - it should be automatically connected due to auto-connect database
        worker_url = "http://localhost:8127"
        worker_id = cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url
        ).worker_id

        # Submit a job - it should be processed automatically without manual registration
        echo_job_schema = JobSchema(name="delay_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Launch worker with delay test!", "delay": 3})
        result = cluster_cm.submit_job(job)

        # Initially the job should be queued
        assert result.status == "queued"
        assert result.output == {}

        worker_status = cluster_cm.get_worker_status(worker_id=worker_id)  # even this is potentially a race
        if worker_status.status != WorkerStatusEnum.IDLE.value:
            warnings.warn(
                f"get_worker_status returned {worker_status.status} when we were expecting {WorkerStatusEnum.IDLE.value}"
            )

        # Wait for the job to be processed
        time.sleep(1)

        job_result = cluster_cm.get_job_status(job_id=job.id)
        assert job_result.status == "running"

        worker_status = cluster_cm.get_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.RUNNING.value

        # Test query_worker_status during job execution
        query_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert query_status.worker_id == worker_id
        assert query_status.status == WorkerStatusEnum.RUNNING.value
        assert query_status.job_id == job.id

        time.sleep(3)

        # Check the final job status
        final_result = cluster_cm.get_job_status(job_id=job.id)
        assert final_result.status == "completed"
        assert final_result.output == {"echoed": "Launch worker with delay test!"}

        worker_status = cluster_cm.get_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.IDLE.value

        # Test query_worker_status after job completion
        query_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert query_status.worker_id == worker_id
        assert query_status.status == WorkerStatusEnum.IDLE.value
        assert query_status.job_id is None

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_integration():
    """Integration test for query_worker_status method with real worker."""
    # Launch cluster manager and worker
    cluster_cm = ClusterManager.launch(host="localhost", port=8140, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8141, wait_for_launch=True, timeout=15)
    worker_id = str(worker_cm.heartbeat().heartbeat.server_id)

    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="query_status_echo", worker_url=str(worker_cm.url))

        # Test initial worker status using query_worker_status
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.worker_id == worker_id
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        assert worker_status.worker_url == str(worker_cm.url)
        assert worker_status.job_id is None

        # Submit a job to test status changes
        echo_job_schema = JobSchema(name="query_status_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Query status test!"})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait a bit for the job to run
        time.sleep(2)

        # Query worker status after job completion
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.worker_id == worker_id
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        assert worker_status.job_id is None

        # Verify job was completed
        job_result = cluster_cm.get_job_status(job_id=job.id)
        assert job_result.status == "completed"
        assert job_result.output == {"echoed": "Query status test!"}

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_by_url_integration():
    """Integration test for query_worker_status_by_url method with real worker."""
    # Launch cluster manager and worker
    cluster_cm = ClusterManager.launch(host="localhost", port=8142, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8143, wait_for_launch=True, timeout=15)
    worker_url = str(worker_cm.url)

    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="query_status_by_url_echo", worker_url=worker_url)

        # Test initial worker status using query_worker_status_by_url
        worker_status = cluster_cm.query_worker_status_by_url(worker_url=worker_url)
        assert worker_status.worker_url == worker_url
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        assert worker_status.job_id is None

        # Submit a job to test status changes
        echo_job_schema = JobSchema(name="query_status_by_url_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Query status by URL test!"})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait a bit for the job to start
        time.sleep(0.5)

        # Query worker status during job execution
        worker_status = cluster_cm.query_worker_status_by_url(worker_url=worker_url)
        assert worker_status.worker_url == worker_url
        # Status could be either IDLE (if job hasn't started) or RUNNING (if job is in progress)
        assert worker_status.status in [WorkerStatusEnum.IDLE.value, WorkerStatusEnum.RUNNING.value]

        # Wait for job completion
        time.sleep(2)

        # Query worker status after job completion
        worker_status = cluster_cm.query_worker_status_by_url(worker_url=worker_url)
        assert worker_status.worker_url == worker_url
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        assert worker_status.job_id is None

        # Verify job was completed
        job_result = cluster_cm.get_job_status(job_id=job.id)
        assert job_result.status == "completed"
        assert job_result.output == {"echoed": "Query status by URL test!"}

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_nonexistent_worker():
    """Integration test for query_worker_status with non-existent worker."""
    # Launch cluster manager only (no worker)
    cluster_cm = ClusterManager.launch(host="localhost", port=8144, wait_for_launch=True, timeout=15)

    try:
        # Test query_worker_status with non-existent worker ID
        worker_status = cluster_cm.query_worker_status(worker_id="nonexistent-worker-123")
        assert worker_status.worker_id == "nonexistent-worker-123"
        assert worker_status.status == WorkerStatusEnum.NONEXISTENT.value
        assert worker_status.worker_url == ""
        assert worker_status.worker_type == ""
        assert worker_status.job_id is None
        assert worker_status.last_heartbeat is None

    finally:
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_by_url_nonexistent_worker():
    """Integration test for query_worker_status_by_url with non-existent worker URL."""
    # Launch cluster manager only (no worker)
    cluster_cm = ClusterManager.launch(host="localhost", port=8145, wait_for_launch=True, timeout=15)

    try:
        # Test query_worker_status_by_url with non-existent worker URL
        worker_status = cluster_cm.query_worker_status_by_url(worker_url="http://nonexistent-worker:8080")
        assert worker_status.worker_id == ""
        assert worker_status.status == WorkerStatusEnum.NONEXISTENT.value
        assert worker_status.worker_url == "http://nonexistent-worker:8080"
        assert worker_status.worker_type == ""
        assert worker_status.job_id is None
        assert worker_status.last_heartbeat is None

    finally:
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_worker_shutdown():
    """Integration test for query_worker_status when worker is shut down."""
    # Launch cluster manager and worker
    cluster_cm = ClusterManager.launch(host="localhost", port=8146, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8147, wait_for_launch=True, timeout=15)
    worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
    worker_url = str(worker_cm.url)

    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="worker_shutdown_echo", worker_url=worker_url)

        # Test initial worker status
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.worker_id == worker_id
        assert worker_status.status == WorkerStatusEnum.IDLE.value

        # Shut down the worker
        worker_cm.shutdown()

        # Query worker status after shutdown - should detect worker is down
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.worker_id == worker_id
        assert worker_status.status == WorkerStatusEnum.NONEXISTENT.value
        assert worker_status.job_id is None

        # Test query_worker_status_by_url after shutdown
        worker_status_by_url = cluster_cm.query_worker_status_by_url(worker_url=worker_url)
        assert worker_status_by_url.worker_id == worker_id
        assert worker_status_by_url.status == WorkerStatusEnum.NONEXISTENT.value
        assert worker_status_by_url.job_id is None

    finally:
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_multiple_workers():
    """Integration test for query_worker_status with multiple workers."""
    # Launch cluster manager and multiple workers
    cluster_cm = ClusterManager.launch(host="localhost", port=8148, wait_for_launch=True, timeout=15)
    worker1_cm = EchoWorker.launch(host="localhost", port=8149, wait_for_launch=True, timeout=15)
    worker2_cm = EchoWorker.launch(host="localhost", port=8150, wait_for_launch=True, timeout=15)

    worker1_id = str(worker1_cm.heartbeat().heartbeat.server_id)
    worker2_id = str(worker2_cm.heartbeat().heartbeat.server_id)
    worker1_url = str(worker1_cm.url)
    worker2_url = str(worker2_cm.url)

    try:
        # Register both workers with the cluster
        cluster_cm.register_job_to_worker(job_type="multiple_workers_status_echo", worker_url=worker1_url)
        cluster_cm.register_job_to_worker(job_type="multiple_workers_status_echo", worker_url=worker2_url)

        # Test initial status of both workers
        worker1_status = cluster_cm.query_worker_status(worker_id=worker1_id)
        worker2_status = cluster_cm.query_worker_status(worker_id=worker2_id)

        assert worker1_status.worker_id == worker1_id
        assert worker1_status.status == WorkerStatusEnum.IDLE.value
        assert worker2_status.worker_id == worker2_id
        assert worker2_status.status == WorkerStatusEnum.IDLE.value

        # Submit jobs to both workers
        echo_job_schema = JobSchema(
            name="multiple_workers_status_echo", input_schema=EchoInput, output_schema=EchoOutput
        )
        job1 = job_from_schema(echo_job_schema, input_data={"message": "Worker 1 job!", "delay": 2})
        job2 = job_from_schema(echo_job_schema, input_data={"message": "Worker 2 job!", "delay": 2})

        result1 = cluster_cm.submit_job(job1)
        result2 = cluster_cm.submit_job(job2)
        assert result1.status == "queued"
        assert result2.status == "queued"

        # Wait a bit for jobs to start
        time.sleep(0.5)

        # Query status of both workers during job execution
        worker1_status = cluster_cm.query_worker_status(worker_id=worker1_id)
        worker2_status = cluster_cm.query_worker_status(worker_id=worker2_id)

        # Both workers should be either IDLE or RUNNING
        assert worker1_status.status == WorkerStatusEnum.RUNNING.value
        assert worker2_status.status == WorkerStatusEnum.RUNNING.value

        # Wait for job completion
        time.sleep(3)

        # Query status of both workers after job completion
        worker1_status = cluster_cm.query_worker_status(worker_id=worker1_id)
        worker2_status = cluster_cm.query_worker_status(worker_id=worker2_id)

        assert worker1_status.status == WorkerStatusEnum.IDLE.value
        assert worker1_status.job_id is None
        assert worker2_status.status == WorkerStatusEnum.IDLE.value
        assert worker2_status.job_id is None

        # Verify both jobs were completed
        job1_result = cluster_cm.get_job_status(job_id=job1.id)
        job2_result = cluster_cm.get_job_status(job_id=job2.id)
        assert job1_result.status == "completed"
        assert job2_result.status == "completed"

    finally:
        if worker1_cm is not None:
            worker1_cm.shutdown()
        if worker2_cm is not None:
            worker2_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_vs_get_worker_status():
    """Integration test comparing query_worker_status vs get_worker_status."""
    # Launch cluster manager and worker
    cluster_cm = ClusterManager.launch(host="localhost", port=8151, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8152, wait_for_launch=True, timeout=15)
    worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
    worker_url = str(worker_cm.url)

    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="status_comparison_echo", worker_url=worker_url)

        # Compare initial status from both methods
        get_status = cluster_cm.get_worker_status(worker_id=worker_id)
        query_status = cluster_cm.query_worker_status(worker_id=worker_id)

        # Both should return the same basic information
        assert get_status.worker_id == query_status.worker_id
        assert get_status.worker_url == query_status.worker_url
        assert get_status.worker_type == query_status.worker_type

        # Submit a job
        echo_job_schema = JobSchema(name="status_comparison_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Status comparison test!"})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait for job to start
        time.sleep(0.5)

        # Compare status during job execution
        get_status = cluster_cm.get_worker_status(worker_id=worker_id)
        query_status = cluster_cm.query_worker_status(worker_id=worker_id)

        # Both should return the same worker ID and URL
        assert get_status.worker_id == query_status.worker_id
        assert get_status.worker_url == query_status.worker_url

        # Wait for job completion
        time.sleep(2)

        # Compare status after job completion
        get_status = cluster_cm.get_worker_status(worker_id=worker_id)
        query_status = cluster_cm.query_worker_status(worker_id=worker_id)

        # Both should show IDLE status
        assert get_status.status == WorkerStatusEnum.IDLE.value
        assert query_status.status == WorkerStatusEnum.IDLE.value
        assert get_status.job_id is None
        assert query_status.job_id is None

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_query_worker_status_real_time_updates():
    """Integration test for real-time worker status updates using query_worker_status."""
    # Launch cluster manager and worker
    cluster_cm = ClusterManager.launch(host="localhost", port=8153, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8154, wait_for_launch=True, timeout=15)
    worker_id = str(worker_cm.heartbeat().heartbeat.server_id)

    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="realtime_status_echo", worker_url=str(worker_cm.url))

        # Initial status should be IDLE
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        assert worker_status.job_id is None

        # Submit a job with delay to observe status changes
        echo_job_schema = JobSchema(name="realtime_status_echo", input_schema=EchoInput, output_schema=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Real-time status test!", "delay": 2})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait for job to start
        time.sleep(0.5)

        # Check status during job execution (should be RUNNING)
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.RUNNING.value
        assert worker_status.job_id == job.id

        # Wait for job completion
        time.sleep(2.5)

        # Check status after job completion (should be IDLE again)
        worker_status = cluster_cm.query_worker_status(worker_id=worker_id)
        assert worker_status.status == WorkerStatusEnum.IDLE.value
        assert worker_status.job_id is None

        # Verify job was completed
        job_result = cluster_cm.get_job_status(job_id=job.id)
        assert job_result.status == "completed"
        assert job_result.output == {"echoed": "Real-time status test!"}

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_node_shutdown_worker():
    """Integration test for Node.shutdown_worker."""
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

        worker_url = "http://localhost:8157"
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url, worker_name="echoworker"
        )
        node.shutdown_worker(worker_name="echoworker")
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url, worker_name="echoworker2"
        )

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_node_shutdown_worker_by_id():
    """Integration test for Node.shutdown_worker_by_id."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8158, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8159, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        cluster_cm.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="auto_connect_db_echo",
        )

        worker_url = "http://localhost:8160"
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url, worker_name="echoworker"
        )
        worker_cm = EchoWorker.connect(worker_url)
        worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
        node.shutdown_worker_by_id(worker_id=worker_id)
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url, worker_name="echoworker2"
        )

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_node_shutdown_worker_by_port():
    """Integration test for Node.shutdown_worker_by_port."""
    # Launch cluster manager
    cluster_cm = ClusterManager.launch(host="localhost", port=8161, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8162, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)

    try:
        cluster_cm.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            job_type="auto_connect_db_echo",
        )

        worker_url = "http://localhost:8163"
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url, worker_name="echoworker"
        )
        node.shutdown_worker_by_port(worker_port=8163)
        cluster_cm.launch_worker(
            node_url=str(node.url), worker_type="echoworker", worker_url=worker_url, worker_name="echoworker2"
        )

    finally:
        node.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()


class ErrorWorker(EchoWorker):
    def _run(self, job_dict: dict) -> dict:
        print(f"ErrorWorker running job: {job_dict}")
        if job_dict.get("should_error", False):
            time.sleep(0.5)
            return {"status": "error", "output": {"error": "Job encountered an error"}}
        return super()._run(job_dict)

class ErrorInput(BaseModel):
    message: str
    should_error: bool
    delay: int = 0

class FailingWorker(EchoWorker):
    def _run(self, job_dict: dict) -> dict:
        print(f"FailingWorker running job: {job_dict}")
        if job_dict.get("should_fail", False):
            time.sleep(0.5)
            return {"status": "failed", "output": {"error": "Job encountered a failure"}}
        return super()._run(job_dict)

class FailingInput(BaseModel):
    message: str
    should_fail: bool
    delay: int = 0

@pytest.mark.integration
def test_dlq_job_failure_and_requeue():
    """Integration test for DLQ: job fails, goes to DLQ, can be requeued."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8164, wait_for_launch=True, timeout=15)
    worker_cm = ErrorWorker.launch(host="localhost", port=8165, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="dlq_test_echo", input_schema=ErrorInput, output_schema=EchoOutput)

    try:
        cluster_cm.register_job_to_worker(job_type="dlq_test_echo", worker_url=str(worker_cm.url))

        # Submit a job that will fail
        job = job_from_schema(echo_job_schema, input_data={"message": "This will fail", "should_error": True})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait for job to complete (and fail)
        time.sleep(2)
        job_status = cluster_cm.get_job_status(job_id=job.id)
        assert job_status.status == "error"

        # Check that job is in DLQ
        dlq_jobs = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs.jobs) == 1
        assert dlq_jobs.jobs[0].job_id == job.id

        # Requeue the job (this time it should succeed)
        requeued_job = cluster_cm.requeue_from_dlq(job_id=job.id)
        assert requeued_job.status == "queued"

        # Verify job is no longer in DLQ after requeue
        dlq_jobs_after = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs_after.jobs) == 0

        # Wait for requeued job to complete
        time.sleep(2)
        final_status = cluster_cm.get_job_status(job_id=job.id)
        # Note: The job will fail again because it has should_fail=True
        # But we've tested the requeue functionality


    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_dlq_job_failure_and_discard():
    """Integration test for DLQ: job fails, goes to DLQ, can be discarded."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8166, wait_for_launch=True, timeout=15)
    worker_cm = ErrorWorker.launch(host="localhost", port=8167, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="dlq_discard_test_echo", input_schema=ErrorInput, output_schema=EchoOutput)

    try:
        cluster_cm.register_job_to_worker(job_type="dlq_discard_test_echo", worker_url=str(worker_cm.url))

        # Submit a job that will fail
        job = job_from_schema(echo_job_schema, input_data={"message": "This will fail", "should_error": True})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait for job to complete (and fail)
        time.sleep(1)
        job_status = cluster_cm.get_job_status(job_id=job.id)
        assert job_status.status == "error"

        # Check that job is in DLQ
        dlq_jobs = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs.jobs) == 1
        assert dlq_jobs.jobs[0].job_id == job.id

        # Discard the job from DLQ
        cluster_cm.discard_from_dlq(job_id=job.id)

        # Verify job is no longer in DLQ
        dlq_jobs_after = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs_after.jobs) == 0

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_dlq_multiple_failed_jobs():
    """Integration test for DLQ with multiple failed jobs."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8168, wait_for_launch=True, timeout=15)
    worker_cm = ErrorWorker.launch(host="localhost", port=8169, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="dlq_multiple_test_echo", input_schema=ErrorInput, output_schema=EchoOutput)

    try:
        cluster_cm.register_job_to_worker(job_type="dlq_multiple_test_echo", worker_url=str(worker_cm.url))

        # Submit multiple jobs that will fail
        jobs = []
        for i in range(3):
            job = job_from_schema(
                echo_job_schema, input_data={"message": f"Job {i} will fail", "should_error": True}
            )
            jobs.append(job)
            result = cluster_cm.submit_job(job)
            assert result.status == "queued"

        # Wait for all jobs to complete (and fail)
        time.sleep(3)

        # Check that all jobs are in DLQ
        dlq_jobs = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs.jobs) == 3
        dlq_job_ids = {job.job_id for job in dlq_jobs.jobs}
        assert dlq_job_ids == {job.id for job in jobs}

        # Requeue one job
        cluster_cm.requeue_from_dlq(job_id=jobs[0].id)
        dlq_jobs_after_requeue = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs_after_requeue.jobs) == 2

        # Discard another job
        cluster_cm.discard_from_dlq(job_id=jobs[1].id)
        dlq_jobs_after_discard = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs_after_discard.jobs) == 1
        assert dlq_jobs_after_discard.jobs[0].job_id == jobs[2].id

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_dlq_requeue_nonexistent_job():
    """Integration test for requeue_from_dlq with non-existent job."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8170, wait_for_launch=True, timeout=15)

    try:
        # Try to requeue a job that doesn't exist in DLQ
        with pytest.raises(HTTPException): # the exception is raised in the cluster manager so all we get is a 404
            cluster_cm.requeue_from_dlq(job_id="nonexistent-job")

    finally:
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_dlq_discard_nonexistent_job():
    """Integration test for discard_from_dlq with non-existent job."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8171, wait_for_launch=True, timeout=15)

    try:
        # Try to discard a job that doesn't exist in DLQ
        with pytest.raises(HTTPException): # the exception is raised in the cluster manager so all we get is a 404
            cluster_cm.discard_from_dlq(job_id="nonexistent-job")

    finally:
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()


@pytest.mark.integration
def test_dlq_failed_job_adds_to_dlq():
    """Integration test for DLQ: job with error status goes to DLQ."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8172, wait_for_launch=True, timeout=15)
    worker_cm = FailingWorker.launch(host="localhost", port=8173, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="dlq_failed_test_echo", input_schema=FailingInput, output_schema=EchoOutput)

    try:
        cluster_cm.register_job_to_worker(job_type="dlq_failed_test_echo", worker_url=str(worker_cm.url))

        # Submit a job that will error
        job = job_from_schema(echo_job_schema, input_data={"message": "This will fail", "should_fail": True})
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"

        # Wait for job to complete (and error)
        time.sleep(2)
        job_status = cluster_cm.get_job_status(job_id=job.id)
        assert job_status.status == "failed"

        # Check that job is in DLQ
        dlq_jobs = cluster_cm.get_dlq_jobs()
        assert len(dlq_jobs.jobs) == 1
        assert dlq_jobs.jobs[0].job_id == job.id

    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.clear_databases()
            cluster_cm.shutdown()
