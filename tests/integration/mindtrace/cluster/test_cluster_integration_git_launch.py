import time

import httpx
import pytest

from mindtrace.cluster import ClusterManager, Node, Worker
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput

from .test_config import GIT_REPO_BRANCH, GIT_REPO_URL


@pytest.mark.integration
def test_start_worker_from_git():
    """Integration test for starting a worker from a git repository."""
    # Use different ports to avoid conflicts with other tests
    cluster_port = 8212
    node_port = 8213
    worker_port = 8214

    # Check for pre-existing services on the ports we'll use (fail fast with clear error)
    ports_to_check = {
        "cluster_manager": cluster_port,
        "node": node_port,
        "worker": worker_port,
    }

    for service_name, port in ports_to_check.items():
        url = f"http://localhost:{port}"
        try:
            # Try to connect to see if something is already running
            response = httpx.post(f"{url}/heartbeat", json={}, timeout=1.0)
            if response.status_code == 200:
                pytest.fail(
                    f"Pre-existing service detected on port {port} ({service_name}). "
                    f"Service at {url} is already running and responding to heartbeat. "
                    f"This test requires clean ports. Please stop any existing Mindtrace services "
                    f"(ClusterManager, Node, or Worker) running on ports {cluster_port}, {node_port}, or {worker_port}."
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            # Port is free, which is what we want
            pass
        except Exception as e:
            # Other errors (like 405 Method Not Allowed) suggest something is on the port
            pytest.fail(
                f"Port {port} ({service_name}) appears to be in use. "
                f"Attempted to check {url}/heartbeat but got unexpected error: {e}. "
                f"This test requires clean ports. Please stop any existing services on ports {cluster_port}, {node_port}, or {worker_port}."
            )

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

        # Launch worker - may timeout if git clone/dependency sync takes too long, but worker might still start
        try:
            cluster_manager.launch_worker(node_url=str(node.url), worker_type="echoworker", worker_url=worker_url)
        except (httpx.ReadTimeout, httpx.TimeoutException) as e:
            # Worker launch timed out, but the worker process might have started anyway.
            # Check if worker is actually responding before failing
            print(f"Worker launch timed out: {e}. Checking if worker started anyway...")

            # Give worker a bit more time to become ready (git clones can take a while)
            max_wait_for_worker = 30  # seconds
            start_time = time.time()
            worker_ready = False
            while (time.time() - start_time) < max_wait_for_worker:
                try:
                    response = httpx.post(f"{worker_url}/heartbeat", json={}, timeout=2.0)
                    if response.status_code == 200:
                        worker_ready = True
                        print(f"Worker is ready after launch timeout (took {time.time() - start_time:.1f}s)")
                        break
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass  # Worker not ready yet, continue waiting
                time.sleep(1)

            if not worker_ready:
                pytest.fail(
                    f"Worker launch timed out after 60s and worker did not become ready within {max_wait_for_worker}s. "
                    f"This indicates the worker failed to launch properly. "
                    f"Git-based worker launches (clone + dependency sync) can take longer than the 60s timeout. "
                    f"Worker URL: {worker_url}"
                )

            # Worker is ready, but launch_worker timed out before completing the setup.
            # We need to manually complete the worker registration to the cluster and job queue.
            # This is what launch_worker does after the worker launches
            print("Completing worker registration to cluster after timeout...")
            try:
                Worker.connect(worker_url)

                # Check if worker auto-connect is configured for this worker type
                worker_auto_connect_list = cluster_manager.worker_auto_connect_database.find(
                    cluster_manager.worker_auto_connect_database.redis_backend.model_cls.worker_type == "echoworker"
                )
                if worker_auto_connect_list:
                    worker_auto_connect = worker_auto_connect_list[0]
                    # Register the worker to the job queue (this connects it to the cluster and starts consuming)
                    cluster_manager.register_job_to_worker(
                        payload={"job_type": worker_auto_connect.schema_name, "worker_url": worker_url}
                    )
                    print(f"Worker registered to job type '{worker_auto_connect.schema_name}' and started consuming")
                else:
                    pytest.fail(
                        "Worker launched but auto-connect configuration not found for worker type 'echoworker'. "
                        "This indicates the worker registration setup is incomplete."
                    )
            except Exception as setup_error:
                pytest.fail(
                    f"Worker launched successfully but failed to complete cluster registration: {setup_error}. "
                    f"This indicates the worker may not be able to consume jobs from the queue."
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
