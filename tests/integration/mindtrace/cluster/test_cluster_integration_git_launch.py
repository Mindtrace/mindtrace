import time

import httpx
import pytest

from mindtrace.cluster import ClusterManager, Node, Worker
from mindtrace.cluster.core.types import LaunchStatusEnum
from mindtrace.core import get_free_port
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput

from .conftest import wait_for_worker_launch
from .test_config import GIT_REPO_BRANCH, GIT_REPO_URL


@pytest.mark.integration
def test_start_worker_from_git():
    """Integration test for starting a worker from a git repository."""
    cluster_port = get_free_port(start_port=8351, end_port=8370)
    node_port = get_free_port(start_port=cluster_port + 1, end_port=8370)
    worker_port = get_free_port(start_port=node_port + 1, end_port=8370)

    cluster_manager = ClusterManager.launch(host="localhost", port=cluster_port, wait_for_launch=True, timeout=15)
    node = Node.launch(
        host="localhost", port=node_port, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
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
        worker_url = f"http://localhost:{worker_port}"

        # Launch worker asynchronously and wait for it to become ready. Git clone
        # and dependency sync can take a while, so we use a generous timeout.
        launch = cluster_manager.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)
        status = wait_for_worker_launch(cluster_manager, str(node.url), launch.launch_id, timeout=150.0)
        if status.status != LaunchStatusEnum.READY:
            pytest.fail(
                f"Worker did not become ready. Status: {status.status}, error: {status.error}. "
                f"Worker URL: {worker_url}"
            )

        # Verify worker is launched and reachable (quick validation to catch launch failures early)
        try:
            response = httpx.post(f"{worker_url}/heartbeat", json={}, timeout=2.0)
            if response.status_code != 200:
                pytest.fail(
                    f"Worker at {worker_url} is not responding correctly. Status code: {response.status_code}. "
                    f"This indicates the worker failed to launch properly or crashed immediately after launch."
                )
        except httpx.TimeoutException:
            pytest.fail(
                f"Worker at {worker_url} did not respond within 2 seconds. "
                f"This indicates the worker failed to launch properly or is not reachable."
            )
        except Exception as e:
            pytest.fail(
                f"Worker at {worker_url} is not reachable. This indicates the worker failed to launch properly. "
                f"Error: {e}"
            )

        # Submit a job and verify it gets processed
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!", "delay": 3})
        result = cluster_manager.submit_job(job)

        # Initially the job should be queued
        assert result.status == "queued", (
            f"Job should be queued immediately after submission, but got status: {result.status}. "
            f"This indicates the job submission system may be malfunctioning."
        )
        assert result.output == {}

        # Wait for job to start running (with timeout and early failure detection)
        max_wait_for_running = 10  # seconds
        start_time = time.time()
        status = result
        while status.status != "running" and (time.time() - start_time) < max_wait_for_running:
            if status.status == "failed":
                pytest.fail(
                    f"Job failed before starting. Status: {status}. "
                    f"This indicates the worker may have crashed, the job was rejected, or there's a job processing error."
                )
            time.sleep(0.5)
            status = cluster_manager.get_job_status(job_id=job.id)

        print(f"Job status after waiting for running: {status}")
        if status.status != "running":
            # Check if worker is still alive
            try:
                response = httpx.post(f"{worker_url}/heartbeat", json={}, timeout=2.0)
                worker_alive = response.status_code == 200
            except Exception:
                worker_alive = False

            pytest.fail(
                f"Job did not transition from 'queued' to 'running' within {max_wait_for_running}s. "
                f"Final status: {status.status}. "
                f"Worker at {worker_url} is {'alive and responding' if worker_alive else 'NOT RESPONDING'}. "
                f"This suggests: "
                f"{'the worker may not be consuming jobs from the queue or there is a queue processing issue' if worker_alive else 'the worker crashed or failed to start properly'}"
            )
        assert status.output == {}

        # Wait for job completion with polling (job has 3s delay, so allow up to 15s total)
        max_wait_for_completion = 15  # seconds
        start_time = time.time()
        final_status = status
        stuck_in_running_count = 0
        while (
            final_status.status != "completed"
            and final_status.status != "failed"
            and (time.time() - start_time) < max_wait_for_completion
        ):
            time.sleep(0.5)
            final_status = cluster_manager.get_job_status(job_id=job.id)

            # Check if job is stuck in running (early failure detection - fail fast if worker is dead)
            if final_status.status == "running":
                stuck_in_running_count += 1
                # If stuck in running for more than 10 seconds (20 checks at 0.5s intervals), check worker health
                if stuck_in_running_count > 20 and (time.time() - start_time) > 10:
                    try:
                        response = httpx.post(f"{worker_url}/heartbeat", json={}, timeout=2.0)
                        worker_alive = response.status_code == 200
                    except Exception:
                        worker_alive = False

                    if not worker_alive:
                        pytest.fail(
                            f"Job stuck in 'running' status and worker at {worker_url} is NOT RESPONDING. "
                            f"Job has been running for {time.time() - start_time:.1f}s (expected ~3s delay + overhead). "
                            f"This indicates the worker crashed during job execution. "
                            f"Current job status: {final_status}"
                        )

        print(f"Final job status: {final_status}")

        # Verify the job completed successfully
        if final_status.status == "failed":
            pytest.fail(
                f"Job failed during execution. Status: {final_status}. "
                f"This indicates the worker encountered an error processing the job."
            )
        assert final_status.status == "completed", (
            f"Job did not complete within {max_wait_for_completion}s. Status: {final_status.status}. "
            f"Current status: {final_status}"
        )
        assert final_status.output == {"echoed": "Hello, World!"}

    finally:
        # Clean up in reverse order
        node.shutdown()
        cluster_manager.clear_databases()
        cluster_manager.shutdown()
