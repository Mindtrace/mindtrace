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

