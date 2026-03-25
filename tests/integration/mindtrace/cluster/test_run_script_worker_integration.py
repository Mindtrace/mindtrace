from functools import partial

import pytest

from mindtrace.cluster.workers.run_script_worker import RunScriptWorkerInput, RunScriptWorkerOutput
from mindtrace.core import get_free_port
from mindtrace.jobs import JobSchema, job_from_schema

from .conftest import wait_for_job_status, wait_for_worker_launch
from .test_config import GIT_REPO_BRANCH, GIT_REPO_URL

free_port = partial(get_free_port, start_port=8371, end_port=8390)


@pytest.mark.integration
def test_run_script_worker_simple(cluster_cm, node):
    """Simple integration test for RunScriptWorker to verify basic functionality."""
    # Define job schema for run script worker
    sample_vbrain_schema = JobSchema(
        name="sample_vbrain",
        input_schema=RunScriptWorkerInput,
        output_schema=RunScriptWorkerOutput,
    )

    # Register the worker type with the cluster
    cluster_cm.register_worker_type(
        worker_name="runscriptworker",
        worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
        worker_params={},
        job_type="sample_vbrain",
    )

    # Launch worker on the node
    worker_url = f"http://localhost:{free_port()}"
    launch = cluster_cm.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
    wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=60.0)

    # Create a simple job that should fail due to missing environment config
    # This tests the error handling of the worker
    job = job_from_schema(
        sample_vbrain_schema,
        input_data={
            "environment": {},  # Empty environment should cause an error
            "command": "echo 'Hello, World!'",
        },
    )

    # Submit job and wait for completion
    cluster_cm.submit_job(job)

    # This job should fail due to invalid environment configuration
    status = wait_for_job_status(cluster_cm, job.id, "failed", timeout=30)
    print(f"Final job status: {status}")


@pytest.mark.integration
def test_run_script_worker_git_environment(cluster_cm, node):
    """Integration test for RunScriptWorker with Git environment."""
    # Define job schema for run script worker
    sample_vbrain_schema = JobSchema(
        name="sample_vbrain",
        input_schema=RunScriptWorkerInput,
        output_schema=RunScriptWorkerOutput,
    )

    # Register the worker type with the cluster
    cluster_cm.register_worker_type(
        worker_name="runscriptworker",
        worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
        worker_params={},
        job_type="sample_vbrain",
    )

    # Launch worker on the node
    worker_url = f"http://localhost:{free_port()}"
    launch = cluster_cm.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
    wait_for_worker_launch(cluster_cm, str(node.url), launch.launch_id, timeout=120.0)

    # Create job with Git environment
    job = job_from_schema(
        sample_vbrain_schema,
        input_data={
            "environment": {
                "git": {
                    "repo_url": GIT_REPO_URL,
                    "branch": GIT_REPO_BRANCH,
                    "working_dir": "",
                }
            },
            "command": "python samples/cluster/run_script/test_script.py",
        },
    )

    # Submit job and wait for completion
    cluster_cm.submit_job(job)

    status = wait_for_job_status(cluster_cm, job.id, "completed", timeout=60)
    print(f"Final job status: {status}")


@pytest.mark.integration
def test_run_script_worker_docker_environment(cluster_cm, node):
    """Integration test for RunScriptWorker with Docker environment."""
    # Define job schema for run script worker
    sample_vbrain_schema = JobSchema(
        name="sample_vbrain",
        input_schema=RunScriptWorkerInput,
        output_schema=RunScriptWorkerOutput,
    )

    # Register the worker type with the cluster
    cluster_cm.register_worker_type(
        worker_name="runscriptworker",
        worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
        worker_params={},
        job_type="sample_vbrain",
    )

    # Launch worker on the node
    worker_url = f"http://localhost:{free_port()}"
    cluster_cm.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)

    # Create job with Docker environment
    job = job_from_schema(
        sample_vbrain_schema,
        input_data={
            "environment": {
                "docker": {
                    "image": "ubuntu:22.04",
                    "environment": {},
                    "volumes": {},
                    "devices": [],
                    "working_dir": "/app",
                }
            },
            "command": "echo 'Hello, World!' && echo 'Goodnight, World!'",
        },
    )

    # Submit job and wait for completion
    cluster_cm.submit_job(job)

    status = wait_for_job_status(cluster_cm, job.id, "completed", timeout=60)
    print(f"Final job status: {status}")


@pytest.mark.integration
def test_run_script_worker_both_environments(cluster_cm, node):
    """Integration test for RunScriptWorker testing both Git and Docker environments in sequence."""
    # Define job schema for run script worker
    sample_vbrain_schema = JobSchema(
        name="sample_vbrain",
        input_schema=RunScriptWorkerInput,
        output_schema=RunScriptWorkerOutput,
    )

    # Register the worker type with the cluster
    cluster_cm.register_worker_type(
        worker_name="runscriptworker",
        worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
        worker_params={},
        job_type="sample_vbrain",
    )

    # Launch worker on the node
    worker_url = f"http://localhost:{free_port()}"
    cluster_cm.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)

    # Test 1: Git environment job
    git_job = job_from_schema(
        sample_vbrain_schema,
        input_data={
            "environment": {
                "git": {
                    "repo_url": GIT_REPO_URL,
                    "branch": GIT_REPO_BRANCH,
                    "working_dir": "",
                }
            },
            "command": "python samples/cluster/run_script/test_script.py",
        },
    )

    cluster_cm.submit_job(git_job)

    # Wait for Git job to complete
    git_status = wait_for_job_status(cluster_cm, git_job.id, "completed", timeout=60)

    # Test 2: Docker environment job
    docker_job = job_from_schema(
        sample_vbrain_schema,
        input_data={
            "environment": {
                "docker": {
                    "image": "ubuntu:22.04",
                    "environment": {},
                    "volumes": {},
                    "devices": [],
                    "working_dir": "/app",
                }
            },
            "command": "echo 'Hello, World!' && echo 'Goodnight, World!'",
        },
    )

    cluster_cm.submit_job(docker_job)

    # Wait for Docker job to complete
    docker_status = wait_for_job_status(cluster_cm, docker_job.id, "completed", timeout=60)

    print("Both jobs completed successfully:")
    print(f"Git job: {git_status}")
    print(f"Docker job: {docker_status}")
