import time

import pytest

from mindtrace.cluster import ClusterManager, Node
from mindtrace.cluster.workers.run_script_worker import RunScriptWorkerInput, RunScriptWorkerOutput
from mindtrace.jobs import JobSchema, job_from_schema


@pytest.mark.integration
def test_run_script_worker_simple():
    """Simple integration test for RunScriptWorker to verify basic functionality."""
    # Use different ports to avoid conflicts with other tests
    cluster_manager = ClusterManager.launch(host="localhost", port=8209, wait_for_launch=True, timeout=15)
    node = Node.launch(
        host="localhost", port=8210, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )
    
    try:
        # Define job schema for run script worker
        sample_vbrain_schema = JobSchema(
            name="sample_vbrain",
            input=RunScriptWorkerInput,
            output=RunScriptWorkerOutput,
        )
        
        # Register the worker type with the cluster
        cluster_manager.register_worker_type(
            worker_name="runscriptworker",
            worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
            worker_params={},
            job_type="sample_vbrain",
        )
        
        # Launch worker on the node
        worker_url = "http://localhost:8211"
        cluster_manager.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
        
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
        cluster_manager.submit_job(job)
        status = cluster_manager.get_job_status(job_id=job.id)
        
        # Wait for job to complete with timeout
        timeout = 30  # 30 seconds timeout
        start_time = time.time()
        while status.status != "completed" and status.status != "failed":
            if time.time() - start_time > timeout:
                pytest.fail(f"Job timed out after {timeout} seconds. Final status: {status}")
            print(f"Job status: {status}")
            time.sleep(1)
            status = cluster_manager.get_job_status(job_id=job.id)
        
        # This job should fail due to invalid environment configuration
        assert status.status == "failed", f"Job should have failed but got status: {status}"
        print(f"Final job status: {status}")
        
    finally:
        # Clean up resources
        if node is not None:
            node.shutdown()
        if cluster_manager is not None:
            cluster_manager.clear_databases()
            cluster_manager.shutdown()


@pytest.mark.integration
def test_run_script_worker_git_environment():
    """Integration test for RunScriptWorker with Git environment."""
    # Use different ports to avoid conflicts with other tests
    cluster_manager = ClusterManager.launch(host="localhost", port=8200, wait_for_launch=True, timeout=15)
    node = Node.launch(
        host="localhost", port=8201, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )
    
    try:
        # Define job schema for run script worker
        sample_vbrain_schema = JobSchema(
            name="sample_vbrain",
            input=RunScriptWorkerInput,
            output=RunScriptWorkerOutput,
        )
        
        # Register the worker type with the cluster
        cluster_manager.register_worker_type(
            worker_name="runscriptworker",
            worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
            worker_params={},
            job_type="sample_vbrain",
        )
        
        # Launch worker on the node
        worker_url = "http://localhost:8202"
        cluster_manager.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
        
        # Create job with Git environment
        job = job_from_schema(
            sample_vbrain_schema,
            input_data={
                "environment": {
                    "git": {
                        "repo_url": "https://github.com/Mindtrace/mindtrace.git",
                        "branch": "feature/cluster/git-and-docker",
                        "working_dir": "",
                    }
                },
                "command": "python samples/cluster/run_script/test_script.py",
            },
        )

        # Submit job and wait for completion
        cluster_manager.submit_job(job)
        status = cluster_manager.get_job_status(job_id=job.id)
        
        # Wait for job to complete with timeout
        timeout = 60  # 60 seconds timeout
        start_time = time.time()
        while status.status != "completed" and status.status != "failed":
            if time.time() - start_time > timeout:
                pytest.fail(f"Job timed out after {timeout} seconds. Final status: {status}")
            print(f"Job status: {status}")
            time.sleep(1)
            status = cluster_manager.get_job_status(job_id=job.id)
        
        # Assert job completed successfully
        assert status.status == "completed", f"Job failed with status: {status}"
        print(f"Final job status: {status}")
        
    finally:
        # Clean up resources
        if node is not None:
            node.shutdown()
        if cluster_manager is not None:
            cluster_manager.clear_databases()
            cluster_manager.shutdown()


@pytest.mark.integration
def test_run_script_worker_docker_environment():
    """Integration test for RunScriptWorker with Docker environment."""
    # Use different ports to avoid conflicts with other tests
    cluster_manager = ClusterManager.launch(host="localhost", port=8203, wait_for_launch=True, timeout=15)
    node = Node.launch(
        host="localhost", port=8204, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )
    
    try:
        # Define job schema for run script worker
        sample_vbrain_schema = JobSchema(
            name="sample_vbrain",
            input=RunScriptWorkerInput,
            output=RunScriptWorkerOutput,
        )
        
        # Register the worker type with the cluster
        cluster_manager.register_worker_type(
            worker_name="runscriptworker",
            worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
            worker_params={},
            job_type="sample_vbrain",
        )
        
        # Launch worker on the node
        worker_url = "http://localhost:8205"
        cluster_manager.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
        
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
        cluster_manager.submit_job(job)
        status = cluster_manager.get_job_status(job_id=job.id)
        
        # Wait for job to complete with timeout
        timeout = 60  # 60 seconds timeout
        start_time = time.time()
        while status.status != "completed" and status.status != "failed":
            if time.time() - start_time > timeout:
                pytest.fail(f"Job timed out after {timeout} seconds. Final status: {status}")
            print(f"Job status: {status}")
            time.sleep(1)
            status = cluster_manager.get_job_status(job_id=job.id)
        
        # Assert job completed successfully
        assert status.status == "completed", f"Job failed with status: {status}"
        print(f"Final job status: {status}")
        
    finally:
        # Clean up resources
        if node is not None:
            node.shutdown()
        if cluster_manager is not None:
            cluster_manager.clear_databases()
            cluster_manager.shutdown()


@pytest.mark.integration
def test_run_script_worker_both_environments():
    """Integration test for RunScriptWorker testing both Git and Docker environments in sequence."""
    # Use different ports to avoid conflicts with other tests
    cluster_manager = ClusterManager.launch(host="localhost", port=8206, wait_for_launch=True, timeout=15)
    node = Node.launch(
        host="localhost", port=8207, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )
    
    try:
        # Define job schema for run script worker
        sample_vbrain_schema = JobSchema(
            name="sample_vbrain",
            input=RunScriptWorkerInput,
            output=RunScriptWorkerOutput,
        )
        
        # Register the worker type with the cluster
        cluster_manager.register_worker_type(
            worker_name="runscriptworker",
            worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
            worker_params={},
            job_type="sample_vbrain",
        )
        
        # Launch worker on the node
        worker_url = "http://localhost:8208"
        cluster_manager.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
        
        # Test 1: Git environment job
        git_job = job_from_schema(
            sample_vbrain_schema,
            input_data={
                "environment": {
                    "git": {
                        "repo_url": "https://github.com/Mindtrace/mindtrace.git",
                        "branch": "feature/cluster/git-and-docker",
                        "working_dir": "",
                    }
                },
                "command": "python samples/cluster/run_script/test_script.py",
            },
        )

        cluster_manager.submit_job(git_job)
        git_status = cluster_manager.get_job_status(job_id=git_job.id)
        
        # Wait for Git job to complete
        timeout = 60
        start_time = time.time()
        while git_status.status != "completed" and git_status.status != "failed":
            if time.time() - start_time > timeout:
                pytest.fail(f"Git job timed out after {timeout} seconds. Final status: {git_status}")
            print(f"Git job status: {git_status}")
            time.sleep(1)
            git_status = cluster_manager.get_job_status(job_id=git_job.id)
        
        assert git_status.status == "completed", f"Git job failed with status: {git_status}"
        
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
        
        cluster_manager.submit_job(docker_job)
        docker_status = cluster_manager.get_job_status(job_id=docker_job.id)
        
        # Wait for Docker job to complete
        start_time = time.time()
        while docker_status.status != "completed" and docker_status.status != "failed":
            if time.time() - start_time > timeout:
                pytest.fail(f"Docker job timed out after {timeout} seconds. Final status: {docker_status}")
            print(f"Docker job status: {docker_status}")
            time.sleep(1)
            docker_status = cluster_manager.get_job_status(job_id=docker_job.id)
        
        assert docker_status.status == "completed", f"Docker job failed with status: {docker_status}"
        
        print(f"Both jobs completed successfully:")
        print(f"Git job: {git_status}")
        print(f"Docker job: {docker_status}")
        
    finally:
        # Clean up resources
        if node is not None:
            node.shutdown()
        if cluster_manager is not None:
            cluster_manager.clear_databases()
            cluster_manager.shutdown() 