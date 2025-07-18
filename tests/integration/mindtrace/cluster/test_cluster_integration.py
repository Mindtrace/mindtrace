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
        cluster_cm.clear_databases()
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
            cluster_cm.clear_databases()
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
            cluster_cm.clear_databases()
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
            cluster_cm.clear_databases()
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
            worker_name="echoworker", 
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", 
            worker_params={}
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
                worker_url=worker_url,
                job_type=None,
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
            job_type="echo"  # This should trigger auto-registration
        )
        
        # Verify that the job schema was automatically registered to the worker type
        # by checking if we can launch a worker and it gets auto-connected
        node = Node.launch(host="localhost", port=8119, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)
        
        try:
            # Launch a worker - it should be automatically connected to the job schema
            worker_url = "http://localhost:8120"
            cluster_cm.launch_worker(
                node_url=str(node.url),
                worker_type="echoworker", 
                worker_url=worker_url
            )
            
            # Submit a job - it should be processed automatically without manual registration
            echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
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
            worker_name="echoworker", 
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", 
            worker_params={}
        )
        
        # Then register the job schema to the worker type
        cluster_cm.register_job_schema_to_worker_type(
            job_schema_name="echo",
            worker_type="echoworker"
        )
        
        # Launch a node and worker
        node = Node.launch(host="localhost", port=8122, cluster_url=str(cluster_cm.url), wait_for_launch=True, timeout=15)
        
        try:
            # Launch a worker - it should be automatically connected due to the registration
            worker_url = "http://localhost:8123"
            cluster_cm.launch_worker(
                node_url=str(node.url),
                worker_type="echoworker", 
                worker_url=worker_url
            )
            
            # Submit a job - it should be processed automatically
            echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
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
            job_schema_name="echo",
            worker_type="nonexistent_worker"
        )
        
        # Verify that no job schema targeting was created
        # (This would be verified by checking that jobs of this type fail to submit)
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Should fail"})
        
        # This should fail because no targeting was created

        result = cluster_cm.submit_job(job)
        assert result.status == "error"
        assert result.output == {"error": "No job schema targeting found for job type echo"}
            
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
            job_type="echo"
        )
        
        # Launch a worker - it should be automatically connected due to auto-connect database
        worker_url = "http://localhost:8127"
        cluster_cm.launch_worker(
            node_url=str(node.url),
            worker_type="echoworker", 
            worker_url=worker_url
        )
        
        # Submit a job - it should be processed automatically without manual registration
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
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
        cluster_cm.launch_worker(
            node_url=str(node.url),
            worker_type="echoworker", 
            worker_url=worker_url
        )
        
        # Submit a job - it should fail because no targeting was created
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Should fail"})
        
        result = cluster_cm.submit_job(job)
        assert result.status == "error"
        assert result.output == {"error": "No job schema targeting found for job type echo"}
        
        # Now manually register the job to the worker
        cluster_cm.register_job_to_worker(job_type="echo", worker_url=worker_url)
        
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
            job_type="echo1"
        )
        
        cluster_cm.register_worker_type(
            worker_name="echoworker2", 
            worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", 
            worker_params={},
            job_type="echo2"
        )
        
        # Launch workers for both types
        worker_url1 = "http://localhost:8133"
        worker_url2 = "http://localhost:8134"
        
        cluster_cm.launch_worker(
            node_url=str(node.url),
            worker_type="echoworker1", 
            worker_url=worker_url1
        )
        
        cluster_cm.launch_worker(
            node_url=str(node.url),
            worker_type="echoworker2", 
            worker_url=worker_url2
        )
        
        # Submit jobs to both workers
        echo_job_schema1 = JobSchema(name="echo1", input=EchoInput, output=EchoOutput)
        echo_job_schema2 = JobSchema(name="echo2", input=EchoInput, output=EchoOutput)
        
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