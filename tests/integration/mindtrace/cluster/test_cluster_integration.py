import time

import pytest

from mindtrace.cluster import ClusterManager, Node
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput


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
        result = cluster_cm.submit_job(job)
        assert result.status == "completed"
        assert result.output == {"echoed": "integration test"}
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
        result = cluster_cm.submit_job(job)
        assert result.status == "queued"
        assert result.output == {}
        time.sleep(1)
        result = cluster_cm.get_job_status(job_id=job.id)
        assert result.status == "completed"
        assert result.output == {"echoed": "Hello, Worker!"}
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
        jobs = []
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
        result = cluster_cm.submit_job(job)
        time.sleep(1)
        assert result.status == "queued"  # Should still succeed but the job is queued
    finally:
        if cluster_cm is not None:
            cluster_cm.shutdown()

@pytest.mark.integration
def test_cluster_manager_with_node():
    """Integration test for ClusterManager with a Node."""
    cluster_cm = ClusterManager.launch(host="localhost", port=8106, wait_for_launch=True, timeout=15)
    node = Node.launch(host="localhost", port=8107, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)
    try:
        cluster_cm.register_worker_type(worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={})
        worker_url = "http://localhost:8108"
        node.launch_worker(worker_type="echoworker", worker_url=worker_url)
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        cluster_cm.register_job_to_worker(job_type="echo", worker_url=worker_url)
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!"})
        result = cluster_cm.submit_job(job)
        time.sleep(1)
        result = cluster_cm.get_job_status(job_id=job.id)
        assert result.status == "completed"
        assert result.output == {"echoed": "Hello, World!"}
    finally:
        node.shutdown()
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
            worker_name="echoworker", 
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", 
            worker_params={}
        )
        
        # Launch a worker using the cluster manager's launch_worker method
        worker_url = "http://localhost:8110"
        cluster_cm.launch_worker(
            node_url=str(node.url),
            worker_type="echoworker", 
            worker_url=worker_url
        )
        
        # Register the worker with the cluster for job processing
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        cluster_cm.register_job_to_worker(job_type="echo", worker_url=worker_url)
        
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
            worker_name="echoworker", 
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", 
            worker_params={}
        )
        
        # Launch multiple workers
        worker_urls = [
            "http://localhost:8113",
            "http://localhost:8114",
            "http://localhost:8115"
        ]
        
        for worker_url in worker_urls:
            cluster_cm.launch_worker(
                node_url=str(node.url),
                worker_type="echoworker", 
                worker_url=worker_url
            )
            # Register each worker
            cluster_cm.register_job_to_worker(job_type="echo", worker_url=worker_url)
        
        # Submit jobs to different workers
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        jobs = []
        
        for i, worker_url in enumerate(worker_urls):
            job = job_from_schema(echo_job_schema, input_data={"message": f"Job {i+1} from worker {worker_url}"})
            jobs.append(job)
            result = cluster_cm.submit_job(job)
            assert result.status == "queued"
        
        # Wait for all jobs to be processed
        time.sleep(3)
        
        # Verify all jobs completed successfully
        for i, job in enumerate(jobs):
            final_result = cluster_cm.get_job_status(job_id=job.id)
            assert final_result.status == "completed"
            assert final_result.output == {"echoed": f"Job {i+1} from worker {worker_urls[i]}"}
        
    finally:
        node.shutdown()
        cluster_cm.shutdown()


@pytest.mark.integration
def test_cluster_manager_launch_worker_node_failure():
    """Integration test for launch_worker when node is not available."""
    # Launch only cluster manager (no node)
    cluster_cm = ClusterManager.launch(host="localhost", port=8116, wait_for_launch=True, timeout=15)
    
    try:
        # Register a worker type
        cluster_cm.register_worker_type(
            worker_name="echoworker", 
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", 
            worker_params={}
        )
        
        # Try to launch a worker on a non-existent node
        with pytest.raises(Exception):
            cluster_cm.launch_worker(
                node_url="http://localhost:9999",  # Non-existent node
                worker_type="echoworker", 
                worker_url="http://localhost:8117"
            )
        
    finally:
        cluster_cm.shutdown()