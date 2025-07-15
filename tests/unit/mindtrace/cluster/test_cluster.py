from unittest.mock import MagicMock, patch, Mock
import multiprocessing
import pytest
from uuid import uuid4

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.core.cluster import ClusterManager, Worker
from mindtrace.jobs import Job, JobSchema, Orchestrator, RabbitMQClient
from mindtrace.jobs.types.job_specs import ExecutionStatus
from mindtrace.services import Service
from mindtrace.database import UnifiedMindtraceODMBackend, BackendType


@pytest.fixture
def cluster_manager():
    # Patch Database to avoid file I/O
    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase:
        mock_database = MockDatabase.return_value
        mock_database.insert = MagicMock()
        mock_database.find = MagicMock(return_value=[])
        mock_database.delete = MagicMock()
        mock_database.redis_backend = MagicMock()
        mock_database.redis_backend.model_cls = MagicMock()
        cm = ClusterManager()
        cm.job_schema_targeting_database = mock_database
        cm.job_status_database = mock_database
        # Patch _url using object.__setattr__ to bypass type checks
        object.__setattr__(cm, "_url", "http://localhost")
        return cm


@pytest.fixture
def mock_worker():
    """Create a mock worker for testing."""
    class MockWorker(Worker):
        def _run(self, job_dict: dict) -> dict:
            return {"status": "completed", "output": {"result": "test"}}
    
    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase:
        mock_database = MockDatabase.return_value
        mock_database.insert = MagicMock()
        mock_database.find = MagicMock(return_value=[])
        mock_database.delete = MagicMock()
        mock_database.redis_backend = MagicMock()
        mock_database.redis_backend.model_cls = MagicMock()
        
        worker = MockWorker()
        object.__setattr__(worker, "_url", "http://localhost:8080")
        worker.id = uuid4()
        return worker


def make_job(schema_name="test_job", payload=None):
    return Job(
        id="jobid",
        name="Test Job",
        schema_name=schema_name,
        payload=payload or {"foo": "bar"},
        status=ExecutionStatus.QUEUED,
        created_at="2024-01-01T00:00:00",
    )


def test_register_job_to_endpoint(cluster_manager):
    payload = cluster_types.RegisterJobToEndpointInput(job_type="test_job", endpoint="/test")
    cluster_manager.register_job_to_endpoint(payload)
    cluster_manager.job_schema_targeting_database.find.assert_called_with(cluster_manager.job_schema_targeting_database.redis_backend.model_cls.schema_name == "test_job")
    cluster_manager.job_schema_targeting_database.insert.assert_called_with(cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test"))


def test_register_job_to_endpoint_with_existing_entries(cluster_manager):
    """Test register_job_to_endpoint when existing entries are found."""
    payload = cluster_types.RegisterJobToEndpointInput(job_type="test_job", endpoint="/test")
    
    # Mock existing entries
    existing_entry = MagicMock()
    existing_entry.pk = "existing-pk"
    cluster_manager.job_schema_targeting_database.find.return_value = [existing_entry]
    
    cluster_manager.register_job_to_endpoint(payload)
    
    # Verify existing entry was deleted
    cluster_manager.job_schema_targeting_database.delete.assert_called_with("existing-pk")
    # Verify new entry was inserted
    cluster_manager.job_schema_targeting_database.insert.assert_called_with(cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test"))


def test_submit_job_success(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")]
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success", "output": {"result": 42}}
        result = cluster_manager.submit_job(job)
        assert result.status == "success"
        assert result.output == {"result": 42}
        mock_post.assert_called_once()


def test_submit_job_registry_reload(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")]
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success", "output": {"result": 42}}
        result = cluster_manager.submit_job(job)
        assert result.status == "success"
        assert result.output == {"result": 42}
        mock_post.assert_called_once()


def test_submit_job_failure(cluster_manager):
    job = make_job(schema_name="unknown_job")
    cluster_manager.job_schema_targeting_database.find.return_value = []
    with pytest.raises(ValueError, match="No job schema targeting found for job type unknown_job"):
        cluster_manager.submit_job(job)


def test_submit_job_to_orchestrator(cluster_manager):
    """Test submit_job when target_endpoint is @orchestrator."""
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="@orchestrator")
    ]
    
    with patch.object(cluster_manager.orchestrator, 'publish') as mock_publish:
        result = cluster_manager.submit_job(job)
        
        # Verify orchestrator was called
        mock_publish.assert_called_once_with("test_job", job)
        # Verify job status was created with queued status
        assert result.status == "queued"
        assert result.worker_id == ""


def test_submit_job_to_endpoint_http_error(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")]
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"
        with pytest.raises(RuntimeError, match="Gateway proxy request failed: Internal Server Error"):
            cluster_manager._submit_job_to_endpoint(job, "/test/test")


def test_submit_job_to_endpoint_json_error(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")]
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.side_effect = Exception("bad json")
        result = cluster_manager._submit_job_to_endpoint(job, "/test/test")
        assert result.status == "completed"
        assert result.output == {}  # fallback on JSON error


def test_register_job_to_worker(cluster_manager):
    """Test register_job_to_worker method."""
    payload = {"job_type": "test_job", "worker_url": "http://worker:8080"}
    
    # Mock existing entries
    existing_entry = MagicMock()
    existing_entry.pk = "existing-pk"
    cluster_manager.job_schema_targeting_database.find.return_value = [existing_entry]
    
    with patch("mindtrace.cluster.core.cluster.Worker") as MockWorker, \
         patch.object(cluster_manager.orchestrator, 'register') as mock_register:
        
        mock_worker_instance = MockWorker.connect.return_value
        
        cluster_manager.register_job_to_worker(payload)
        
        # Verify existing entry was deleted
        cluster_manager.job_schema_targeting_database.delete.assert_called_with("existing-pk")
        # Verify new entry was inserted with @orchestrator target
        cluster_manager.job_schema_targeting_database.insert.assert_called_with(
            cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="@orchestrator")
        )
        # Verify orchestrator registration
        mock_register.assert_called_once()
        # Verify worker connection
        MockWorker.connect.assert_called_once_with("http://worker:8080")
        mock_worker_instance.connect_to_cluster.assert_called_once()


def test_register_job_to_worker_with_existing_entries(cluster_manager):
    """Test register_job_to_worker when existing entries are found."""
    payload = {"job_type": "test_job", "worker_url": "http://worker:8080"}
    
    # Mock existing entries
    existing_entry = MagicMock()
    existing_entry.pk = "existing-pk"
    cluster_manager.job_schema_targeting_database.find.return_value = [existing_entry]
    
    with patch("mindtrace.cluster.core.cluster.Worker") as MockWorker, \
         patch.object(cluster_manager.orchestrator, 'register') as mock_register:
        
        mock_worker_instance = MockWorker.connect.return_value
        
        cluster_manager.register_job_to_worker(payload)
        
        # Verify existing entry was deleted
        cluster_manager.job_schema_targeting_database.delete.assert_called_with("existing-pk")


def test_get_job_status_success(cluster_manager):
    """Test get_job_status when job exists."""
    job_id = "test-job-123"
    expected_job_status = cluster_types.JobStatus(
        job_id=job_id,
        status="running",
        output={"result": "test"},
        worker_id="worker-123"
    )
    
    cluster_manager.job_status_database.find.return_value = [expected_job_status]
    
    payload = {"job_id": job_id}
    result = cluster_manager.get_job_status(payload)
    
    assert result == expected_job_status
    cluster_manager.job_status_database.find.assert_called_with(
        cluster_manager.job_status_database.redis_backend.model_cls.job_id == job_id
    )


def test_get_job_status_not_found(cluster_manager):
    """Test get_job_status when job doesn't exist."""
    job_id = "nonexistent-job"
    cluster_manager.job_status_database.find.return_value = []
    
    payload = {"job_id": job_id}
    
    with pytest.raises(ValueError, match=f"Job status not found for job id {job_id}"):
        cluster_manager.get_job_status(payload)


def test_worker_alert_started_job(cluster_manager):
    """Test worker_alert_started_job method."""
    job_id = "test-job-123"
    worker_id = "worker-456"
    
    # Mock existing job status
    existing_job_status = cluster_types.JobStatus(
        job_id=job_id,
        status="queued",
        output={},
        worker_id=""
    )
    cluster_manager.job_status_database.find.return_value = [existing_job_status]
    
    payload = {"job_id": job_id, "worker_id": worker_id}
    cluster_manager.worker_alert_started_job(payload)
    
    # Verify job status was updated and saved
    assert existing_job_status.status == "running"
    assert existing_job_status.worker_id == worker_id
    cluster_manager.job_status_database.insert.assert_called_with(existing_job_status)


def test_worker_alert_started_job_not_found(cluster_manager):
    """Test worker_alert_started_job when job doesn't exist."""
    job_id = "nonexistent-job"
    worker_id = "worker-456"
    
    cluster_manager.job_status_database.find.return_value = []
    
    payload = {"job_id": job_id, "worker_id": worker_id}
    
    with pytest.raises(ValueError, match=f"Job status not found for job id {job_id}"):
        cluster_manager.worker_alert_started_job(payload)


def test_worker_alert_completed_job(cluster_manager):
    """Test worker_alert_completed_job method."""
    job_id = "test-job-123"
    status = "completed"
    output = {"result": "success"}
    
    # Mock existing job status
    existing_job_status = cluster_types.JobStatus(
        job_id=job_id,
        status="running",
        output={},
        worker_id="worker-123"
    )
    cluster_manager.job_status_database.find.return_value = [existing_job_status]
    
    payload = {"job_id": job_id, "status": status, "output": output}
    cluster_manager.worker_alert_completed_job(payload)
    
    # Verify job status was updated and saved
    assert existing_job_status.status == status
    assert existing_job_status.output == output
    cluster_manager.job_status_database.insert.assert_called_with(existing_job_status)


def test_worker_alert_completed_job_not_found(cluster_manager):
    """Test worker_alert_completed_job when job doesn't exist."""
    job_id = "nonexistent-job"
    status = "completed"
    output = {"result": "success"}
    
    cluster_manager.job_status_database.find.return_value = []
    
    payload = {"job_id": job_id, "status": status, "output": output}
    
    with pytest.raises(ValueError, match=f"Job status not found for job id {job_id}"):
        cluster_manager.worker_alert_completed_job(payload)


# Worker class tests
def test_worker_initialization(mock_worker):
    """Test Worker initialization."""
    assert mock_worker.consume_process is None
    assert mock_worker._cluster_connection_manager is None
    assert mock_worker._cluster_url is None


def test_worker_cluster_connection_manager_property(mock_worker):
    """Test cluster_connection_manager property."""
    # Initially should be None
    assert mock_worker.cluster_connection_manager is None
    
    # Set cluster URL
    mock_worker._cluster_url = "http://cluster:8080"
    
    with patch("mindtrace.cluster.core.cluster.ClusterManager") as MockClusterManager:
        mock_cm_instance = MockClusterManager.connect.return_value
        
        # Should create connection manager
        result = mock_worker.cluster_connection_manager
        
        assert result == mock_cm_instance
        MockClusterManager.connect.assert_called_once_with("http://cluster:8080")
        
        # Should cache the result
        result2 = mock_worker.cluster_connection_manager
        assert result2 == mock_cm_instance
        # Should not call connect again
        assert MockClusterManager.connect.call_count == 1


def test_worker_run_with_cluster_manager(mock_worker):
    """Test Worker.run method with cluster connection manager."""
    job_dict = {"id": "test-job", "payload": {"test": "data"}}
    
    # Mock cluster connection manager
    mock_cm = MagicMock()
    mock_worker._cluster_connection_manager = mock_cm
    
    result = mock_worker.run(job_dict)
    
    # Verify cluster manager was called
    mock_cm.worker_alert_started_job.assert_called_once_with(job_id="test-job", worker_id=str(mock_worker.id))
    mock_cm.worker_alert_completed_job.assert_called_once_with(
        job_id="test-job", 
        status="completed", 
        output={"result": "test"}
    )
    
    # Verify result
    assert result["status"] == "completed"
    assert result["output"]["result"] == "test"


def test_worker_run_without_cluster_manager(mock_worker):
    """Test Worker.run method without cluster connection manager."""
    job_dict = {"id": "test-job", "payload": {"test": "data"}}
    
    # Ensure no cluster connection manager
    mock_worker._cluster_connection_manager = None
    
    result = mock_worker.run(job_dict)
    
    # Should still work without cluster manager
    assert result["status"] == "completed"
    assert result["output"]["result"] == "test"


def test_worker_start_method(mock_worker):
    """Test Worker.start method."""
    # The start method should be callable and not raise any exceptions
    result = mock_worker.start()
    assert result is None  # start() returns None by default


def test_worker_connect_to_cluster(mock_worker):
    """Test Worker.connect_to_cluster method."""
    backend_args = {"cls": "test.backend", "kwargs": {"host": "localhost"}}
    queue_name = "test_queue"
    cluster_url = "http://cluster:8080"
    
    payload = {
        "backend_args": backend_args,
        "queue_name": queue_name,
        "cluster_url": cluster_url
    }
    
    with patch.object(mock_worker, 'start') as mock_start, \
         patch.object(mock_worker, 'connect_to_orchestator_via_backend_args') as mock_connect, \
         patch.object(mock_worker, 'consume') as mock_consume, \
         patch('multiprocessing.Process') as MockProcess:
        
        mock_process = MockProcess.return_value
        
        mock_worker.connect_to_cluster(payload)
        
        # Verify cluster URL was set
        assert mock_worker._cluster_url == cluster_url
        
        # Verify start was called
        mock_start.assert_called_once()
        
        # Verify orchestrator connection
        mock_connect.assert_called_once_with(backend_args, queue_name=queue_name)
        
        # Verify process was created and started
        MockProcess.assert_called_once_with(target=mock_consume)
        mock_process.start.assert_called_once()
        
        # Verify consume process was stored
        assert mock_worker.consume_process == mock_process


def test_worker_shutdown_with_process(mock_worker):
    """Test Worker.shutdown method when consume process exists."""
    # Mock consume process
    mock_process = MagicMock()
    mock_worker.consume_process = mock_process
    
    with patch.object(Service, 'shutdown') as mock_service_shutdown:
        mock_worker.shutdown()
        
        # Verify process was killed
        mock_process.kill.assert_called_once()
        
        # Verify service shutdown was called
        mock_service_shutdown.assert_called_once()


def test_worker_shutdown_without_process(mock_worker):
    """Test Worker.shutdown method when no consume process exists."""
    # Ensure no consume process
    mock_worker.consume_process = None
    
    with patch.object(Service, 'shutdown') as mock_service_shutdown:
        mock_worker.shutdown()
        
        # Verify service shutdown was called
        mock_service_shutdown.assert_called_once()


def test_worker_abstract_run_method():
    """Test that Worker._run method is abstract."""
    # Create a Worker instance (should work since we're not calling _run)
    worker = Worker()
    
    # Verify _run method exists and is abstract
    assert hasattr(worker, '_run')
    assert hasattr(worker._run, '__isabstractmethod__')


def test_worker_concrete_implementation():
    """Test a concrete Worker implementation."""
    class ConcreteWorker(Worker):
        def _run(self, job_dict: dict) -> dict:
            return {"status": "success", "output": {"processed": job_dict}}
    
    worker = ConcreteWorker()
    job_dict = {"test": "data"}
    
    result = worker._run(job_dict)
    assert result["status"] == "success"
    assert result["output"]["processed"] == job_dict
