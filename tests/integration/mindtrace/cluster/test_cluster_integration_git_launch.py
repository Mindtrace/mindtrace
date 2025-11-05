import time

import pytest

from mindtrace.cluster import ClusterManager, Node
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput

from .test_config import GIT_REPO_BRANCH, GIT_REPO_URL


@pytest.mark.integration
def test_start_worker_from_git():
    """Integration test for starting a worker from a git repository."""
    # Use different ports to avoid conflicts with other tests
    cluster_manager = ClusterManager.launch(host="localhost", port=8212, wait_for_launch=True, timeout=15)
    node = Node.launch(
        host="localhost", port=8213, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )

    try:
        echo_job_schema = JobSchema(name="echo", input_schema=EchoInput, output_schema=EchoOutput)

        # Register worker type with git repository information
        cluster_manager.register_worker_type(
            worker_name="echoworker",
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
            worker_params={},
            git_repo_url=GIT_REPO_URL,
            git_branch=GIT_REPO_BRANCH,
            job_type="echo",
        )

        # Launch worker on the node
        worker_url = "http://localhost:8214"
        cluster_manager.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)

        # Submit a job and verify it gets processed
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!", "delay": 3})
        result = cluster_manager.submit_job(job)

        # Initially the job should be queued
        assert result.status == "queued"
        assert result.output == {}

        # Check job status after a short delay
        time.sleep(1)
        status_after_1s = cluster_manager.get_job_status(job_id=job.id)
        print(f"Job status after 1s: {status_after_1s}")
        assert status_after_1s.status == "running"
        assert status_after_1s.output == {}

        # Wait for job completion and verify final status
        time.sleep(5)
        final_status = cluster_manager.get_job_status(job_id=job.id)
        print(f"Final job status: {final_status}")

        # Verify the job completed successfully
        assert final_status.status == "completed"
        assert final_status.output == {"echoed": "Hello, World!"}

    finally:
        # Clean up in reverse order
        node.shutdown()
        cluster_manager.clear_databases()
        cluster_manager.shutdown()
