import pytest

from mindtrace.cluster import ClusterManager
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput, EchoService
from mindtrace.cluster.workers.echo_worker import EchoWorker


@pytest.mark.integration
def test_cluster_manager_as_gateway():
    echo_job = JobSchema(name="echo_job", input=EchoInput, output=EchoOutput)

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
        cluster_cm.register_job_to_endpoint(job_type="echo_job", endpoint="echo/run")
        job = job_from_schema(echo_job, EchoInput(message="integration test"))
        result = cluster_cm.submit_job(**job.model_dump())
        assert result.status == "success"
        assert result.output == "integration test"
    finally:
        # Clean up in reverse order
        echo_cm.shutdown()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_with_prelaunched_worker():
    """Integration test for ClusterManager with a prelaunched EchoWorker."""
    # Use different ports to avoid conflicts with other tests
    cluster_cm = ClusterManager.launch(host="localhost", port=8100, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8101, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
    try:
        # Register the worker with the cluster
        cluster_cm.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))
        # Submit a job
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, Worker!"})
        result = cluster_cm.submit_job(**job.model_dump())
        assert result.status == "success"
    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_multiple_jobs_with_worker():
    """Integration test for submitting multiple jobs to a prelaunched EchoWorker."""
    from mindtrace.cluster.workers.echo_worker import EchoWorker
    cluster_cm = ClusterManager.launch(host="localhost", port=8102, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8103, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
    try:
        cluster_cm.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))
        messages = ["Job 1", "Job 2", "Job 3"]
        for msg in messages:
            job = job_from_schema(echo_job_schema, input_data={"message": msg})
            result = cluster_cm.submit_job(**job.model_dump())
            assert result.status == "success"
    finally:
        if worker_cm is not None:
            worker_cm.shutdown()
        if cluster_cm is not None:
            cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_worker_failure():
    """Integration test for handling worker failure (simulate by shutting down worker before job submission)."""
    from mindtrace.cluster.workers.echo_worker import EchoWorker
    cluster_cm = ClusterManager.launch(host="localhost", port=8104, wait_for_launch=True, timeout=15)
    worker_cm = EchoWorker.launch(host="localhost", port=8105, wait_for_launch=True, timeout=15)
    echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
    try:
        cluster_cm.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))
        # Shut down the worker before submitting the job
        worker_cm.shutdown()
        job = job_from_schema(echo_job_schema, input_data={"message": "Should fail"})
        result = cluster_cm.submit_job(**job.model_dump())
        assert result.status == "success"  # Should still succeed but the job is queued
    finally:
        if cluster_cm is not None:
            cluster_cm.shutdown()
