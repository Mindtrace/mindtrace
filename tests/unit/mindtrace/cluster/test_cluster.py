import copy
from unittest.mock import MagicMock, patch, ANY
from uuid import uuid4

import pytest

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.core.cluster import ClusterManager, Worker, Node
from mindtrace.cluster.workers.standard_worker_launcher import ProxyWorker
from mindtrace.jobs import Job
from mindtrace.jobs.types.job_specs import ExecutionStatus
from mindtrace.services import Service


@pytest.fixture
def cluster_manager():
    # Patch Database to avoid file I/O
    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase, \
            patch("mindtrace.cluster.core.cluster.RabbitMQClient") as MockRabbitMQClient, \
            patch("mindtrace.cluster.core.cluster.MinioRegistryBackend") as MockMinioBackend:
        
        def create_mock_database():
            mock_database = MagicMock()
            mock_database.insert = MagicMock()
            mock_database.find = MagicMock(return_value=[])
            mock_database.delete = MagicMock()
            mock_database.redis_backend = MagicMock()
            mock_database.redis_backend.model_cls = MagicMock()
            return mock_database
        
        MockDatabase.side_effect = [create_mock_database(), create_mock_database(), create_mock_database()]

        mock_rabbitmq_client = MockRabbitMQClient.return_value
        mock_rabbitmq_client.publish = MagicMock()
        mock_rabbitmq_client.register = MagicMock()
        mock_minio_backend = MockMinioBackend.return_value
        mock_minio_backend.load = MagicMock()
        mock_minio_backend.save = MagicMock()
        mock_minio_backend.delete = MagicMock()
        mock_minio_backend.list = MagicMock()
        mock_minio_backend.get = MagicMock()
        mock_logger = MagicMock()
        mock_logger.error = MagicMock() 
        mock_logger.info = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.debug = MagicMock()
        mock_logger.critical = MagicMock()
        mock_logger.exception = MagicMock()
        mock_logger.fatal = MagicMock()
        mock_logger.trace = MagicMock()

        cm = ClusterManager()
        cm.logger = mock_logger
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
    result = cluster_manager.submit_job(job)    
    assert result.status == "error"
    assert result.output == {"error": "No job schema targeting found for job type unknown_job"}


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
    
    with patch("mindtrace.cluster.core.cluster.Worker"), \
         patch.object(cluster_manager.orchestrator, 'register'):
        
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
    
    payload = {"job_id": job_id, "status": status, "output": output, "worker_id": "worker-123"}
    cluster_manager.worker_alert_completed_job(payload)
    
    # Verify job status was updated and saved
    assert existing_job_status.status == status
    assert existing_job_status.output == output
    cluster_manager.job_status_database.insert.assert_called_with(existing_job_status)


def test_worker_alert_completed_job_not_found(cluster_manager):
    """Test worker_alert_completed_job when job doesn't exist."""
    job_id = "nonexistent-job"
    cluster_manager.job_status_database.find.return_value = []
    
    payload = {"job_id": job_id, "worker_id": "worker-123", "status": "completed", "output": {"result": "test"}}
    
    with pytest.raises(ValueError, match=f"Job status not found for job id {job_id}"):
        cluster_manager.worker_alert_completed_job(payload)


def test_register_worker_type(cluster_manager):
    """Test register_worker_type method."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "mindtrace.cluster.workers.standard_worker_launcher.StandardWorkerLauncher",
        "worker_params": {"param1": "value1"},
        "materializer_name": "custom.materializer.CustomMaterializer",
        "job_type": None
    }
    
    with patch.object(cluster_manager.worker_registry, 'register_materializer') as mock_register_materializer, \
         patch.object(cluster_manager.worker_registry, 'save') as mock_save:
        
        cluster_manager.register_worker_type(payload)
        
        # Verify materializer was registered
        mock_register_materializer.assert_called_once()
        # Verify worker was saved
        mock_save.assert_called_once_with("worker:test_worker", ANY)


def test_register_worker_type_with_default_materializer(cluster_manager):
    """Test register_worker_type method with default materializer."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "mindtrace.cluster.workers.standard_worker_launcher.StandardWorkerLauncher",
        "worker_params": {"param1": "value1"},
        "materializer_name": None,
        "job_type": None
    }
    
    with patch.object(cluster_manager.worker_registry, 'register_materializer') as mock_register_materializer, \
         patch.object(cluster_manager.worker_registry, 'save') as mock_save:
        
        cluster_manager.register_worker_type(payload)
        
        # Verify materializer was registered with default name
        mock_register_materializer.assert_called_once()
        # Verify worker was saved
        mock_save.assert_called_once_with("worker:test_worker", ANY)


def test_register_worker_type_with_job_schema_name(cluster_manager):
    """Test register_worker_type when job_schema_name is provided."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "mindtrace.cluster.workers.test_worker.TestWorker",
        "worker_params": {"param1": "value1"},
        "materializer_name": None,
        "job_type": "test_job"
    }
    
    with patch("mindtrace.cluster.core.cluster.ProxyWorker") as MockProxyWorker, \
         patch.object(cluster_manager.worker_registry, 'register_materializer') as mock_register_materializer, \
         patch.object(cluster_manager.worker_registry, 'save') as mock_save, \
         patch.object(cluster_manager, 'register_job_schema_to_worker_type') as mock_register_job_schema:
        
        mock_proxy_worker = MockProxyWorker.return_value
        
        cluster_manager.register_worker_type(payload)
        
        # Verify ProxyWorker was created and saved
        MockProxyWorker.assert_called_once_with(
            worker_type="mindtrace.cluster.workers.test_worker.TestWorker",
            worker_params={"param1": "value1"}
        )
        mock_save.assert_called_once_with("worker:test_worker", mock_proxy_worker)
        
        # Verify job schema was registered to worker type
        mock_register_job_schema.assert_called_once_with({
            "job_schema_name": "test_job", 
            "worker_type": "test_worker"
        })


def test_register_job_schema_to_worker_type_success(cluster_manager):
    """Test register_job_schema_to_worker_type when worker type exists in registry."""
    payload = {
        "job_schema_name": "test_job",
        "worker_type": "test_worker"
    }
    
    with patch.object(cluster_manager.worker_registry, 'has_object', return_value=True) as mock_has_object, \
         patch.object(cluster_manager.job_schema_targeting_database, 'insert') as mock_insert_targeting, \
         patch.object(cluster_manager.worker_auto_connect_database, 'insert') as mock_insert_auto_connect:
        
        cluster_manager.register_job_schema_to_worker_type(payload)
        
        # Verify worker type exists check
        mock_has_object.assert_called_once_with("worker:test_worker")
        
        # Verify job schema targeting was inserted
        mock_insert_targeting.assert_called_once_with(
            cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="@orchestrator")
        )
        
        # Verify worker auto connect was inserted
        mock_insert_auto_connect.assert_called_once_with(
            cluster_types.WorkerAutoConnect(worker_type="test_worker", schema_name="test_job")
        )


def test_register_job_schema_to_worker_type_worker_not_found(cluster_manager):
    """Test register_job_schema_to_worker_type when worker type doesn't exist in registry."""
    payload = {
        "job_schema_name": "test_job",
        "worker_type": "nonexistent_worker"
    }
    
    with patch.object(cluster_manager.worker_registry, 'has_object', return_value=False) as mock_has_object, \
         patch.object(cluster_manager.job_schema_targeting_database, 'insert') as mock_insert_targeting, \
         patch.object(cluster_manager.worker_auto_connect_database, 'insert') as mock_insert_auto_connect:
        
        cluster_manager.register_job_schema_to_worker_type(payload)
        
        # Verify worker type exists check
        mock_has_object.assert_called_once_with("worker:nonexistent_worker")
        
        # Verify no database insertions occurred
        mock_insert_targeting.assert_not_called()
        mock_insert_auto_connect.assert_not_called()


def test_launch_worker_with_auto_connect(cluster_manager):
    """Test launch_worker when worker is in auto-connect database."""
    payload = {
        "node_url": "http://node:8080",
        "worker_type": "test_worker",
        "worker_url": "http://worker:8081"
    }
    
    # Mock auto-connect entry
    auto_connect_entry = cluster_types.WorkerAutoConnect(
        worker_type="test_worker",
        schema_name="test_job"
    )
    cluster_manager.worker_auto_connect_database.find.return_value = [auto_connect_entry]
    
    with patch("mindtrace.cluster.core.cluster.Node") as MockNode, \
         patch.object(cluster_manager, 'register_job_to_worker') as mock_register_job:
        
        mock_node_instance = MockNode.connect.return_value
        
        cluster_manager.launch_worker(payload)
        
        # Verify node connection and worker launch
        MockNode.connect.assert_called_once_with("http://node:8080")
        mock_node_instance.launch_worker.assert_called_once_with(
            worker_type="test_worker",
            worker_url="http://worker:8081"
        )
        
        # Verify auto-connect registration
        mock_register_job.assert_called_once_with(payload={
            "job_type": "test_job",
            "worker_url": "http://worker:8081"
        })


def test_launch_worker_without_auto_connect(cluster_manager):
    """Test launch_worker when worker is not in auto-connect database."""
    payload = {
        "node_url": "http://node:8080",
        "worker_type": "test_worker",
        "worker_url": "http://worker:8081"
    }
    
    # Mock no auto-connect entries
    cluster_manager.worker_auto_connect_database.find.return_value = []
    
    with patch("mindtrace.cluster.core.cluster.Node") as MockNode, \
         patch.object(cluster_manager, 'register_job_to_worker') as mock_register_job:
        
        mock_node_instance = MockNode.connect.return_value
        
        cluster_manager.launch_worker(payload)
        
        # Verify node connection and worker launch
        MockNode.connect.assert_called_once_with("http://node:8080")
        mock_node_instance.launch_worker.assert_called_once_with(
            worker_type="test_worker",
            worker_url="http://worker:8081"
        )
        
        # Verify no auto-connect registration occurred
        mock_register_job.assert_not_called()


def test_launch_worker_node_connection_failure(cluster_manager):
    """Test launch_worker when node connection fails."""
    payload = {
        "node_url": "http://node:8080",
        "worker_type": "test_worker",
        "worker_url": "http://worker:8081"
    }
    
    with patch("mindtrace.cluster.core.cluster.Node") as MockNode:
        MockNode.connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception, match="Connection failed"):
            cluster_manager.launch_worker(payload)


def test_launch_worker_node_launch_failure(cluster_manager):
    """Test launch_worker when node worker launch fails."""
    payload = {
        "node_url": "http://node:8080",
        "worker_type": "test_worker",
        "worker_url": "http://worker:8081"
    }
    
    with patch("mindtrace.cluster.core.cluster.Node") as MockNode:
        mock_node_instance = MockNode.connect.return_value
        mock_node_instance.launch_worker.side_effect = Exception("Launch failed")
        
        with pytest.raises(Exception, match="Launch failed"):
            cluster_manager.launch_worker(payload)


def test_launch_worker_with_different_ports(cluster_manager):
    """Test launch_worker with different node and worker ports."""
    payload = {
        "node_url": "http://node:9090",
        "worker_type": "test_worker",
        "worker_url": "http://worker:9091"
    }
    
    # Mock auto-connect entry
    auto_connect_entry = cluster_types.WorkerAutoConnect(
        worker_type="test_worker",
        schema_name="test_job"
    )
    cluster_manager.worker_auto_connect_database.find.return_value = [auto_connect_entry]
    
    with patch("mindtrace.cluster.core.cluster.Node") as MockNode, \
         patch.object(cluster_manager, 'register_job_to_worker') as mock_register_job:
        
        mock_node_instance = MockNode.connect.return_value
        
        cluster_manager.launch_worker(payload)
        
        # Verify correct URLs were used
        MockNode.connect.assert_called_once_with("http://node:9090")
        mock_node_instance.launch_worker.assert_called_once_with(
            worker_type="test_worker",
            worker_url="http://worker:9091"
        )
        mock_register_job.assert_called_once_with(payload={
            "job_type": "test_job",
            "worker_url": "http://worker:9091"
        })


def test_launch_worker_logging(cluster_manager):
    """Test launch_worker logging behavior."""
    payload = {
        "node_url": "http://node:8080",
        "worker_type": "test_worker",
        "worker_url": "http://worker:8081"
    }
    
    # Mock auto-connect entry
    auto_connect_entry = cluster_types.WorkerAutoConnect(
        worker_type="test_worker",
        schema_name="test_job"
    )
    cluster_manager.worker_auto_connect_database.find.return_value = [auto_connect_entry]
    
    with patch("mindtrace.cluster.core.cluster.Node") as MockNode, \
         patch.object(cluster_manager, 'register_job_to_worker') as mock_register_job, \
         patch.object(cluster_manager, 'logger') as mock_logger:
        
        mock_node_instance = MockNode.connect.return_value
        
        cluster_manager.launch_worker(payload)
        
        # Verify logging occurred (the actual log calls would be verified in integration tests)
        # This test ensures the method completes without errors and calls the expected methods
        MockNode.connect.assert_called_once()
        mock_node_instance.launch_worker.assert_called_once()
        mock_register_job.assert_called_once()


def test_register_node(cluster_manager):
    """Test register_node method."""
    payload = {"node_url": "http://localhost:8001"}
    
    result = cluster_manager.register_node(payload)
    
    expected_result = {
        "endpoint": cluster_manager.worker_registry_endpoint,
        "access_key": cluster_manager.worker_registry_access_key,
        "secret_key": cluster_manager.worker_registry_secret_key,
        "bucket": cluster_manager.worker_registry_bucket
    }
    
    assert result == expected_result
    assert "http://localhost:8001" in cluster_manager.nodes


def test_clear_databases_empty_databases(cluster_manager):
    """Test clear_databases when all databases are empty."""
    # Mock empty databases
    cluster_manager.job_schema_targeting_database.all.return_value = []
    cluster_manager.job_status_database.all.return_value = []
    cluster_manager.worker_auto_connect_database.all.return_value = []
    
    cluster_manager.clear_databases()
    
    # Verify all() was called on each database
    cluster_manager.job_schema_targeting_database.all.assert_called_once()
    cluster_manager.job_status_database.all.assert_called_once()
    cluster_manager.worker_auto_connect_database.all.assert_called_once()
    
    # Verify delete was never called since databases are empty
    cluster_manager.job_schema_targeting_database.delete.assert_not_called()
    cluster_manager.job_status_database.delete.assert_not_called()
    cluster_manager.worker_auto_connect_database.delete.assert_not_called()
    
    # Verify logging
    cluster_manager.logger.info.assert_called_once_with("Cleared all cluster manager databases")


def test_clear_databases_with_entries(cluster_manager):
    """Test clear_databases when databases contain entries."""
    # Mock entries in databases
    mock_entry1 = MagicMock()
    mock_entry1.pk = "pk1"
    mock_entry2 = MagicMock()
    mock_entry2.pk = "pk2"
    mock_entry3 = MagicMock()
    mock_entry3.pk = "pk3"
    
    cluster_manager.job_schema_targeting_database.all.return_value = [mock_entry1]
    cluster_manager.job_status_database.all.return_value = [mock_entry2]
    cluster_manager.worker_auto_connect_database.all.return_value = [mock_entry3]
    
    cluster_manager.clear_databases()
    
    # Verify all() was called on each database
    cluster_manager.job_schema_targeting_database.all.assert_called_once()
    cluster_manager.job_status_database.all.assert_called_once()
    cluster_manager.worker_auto_connect_database.all.assert_called_once()
    
    # Verify delete was called for each entry
    cluster_manager.job_schema_targeting_database.delete.assert_called_once_with("pk1")
    cluster_manager.job_status_database.delete.assert_called_once_with("pk2")
    cluster_manager.worker_auto_connect_database.delete.assert_called_once_with("pk3")
    
    # Verify logging
    cluster_manager.logger.info.assert_called_once_with("Cleared all cluster manager databases")


def test_clear_databases_multiple_entries_per_database(cluster_manager):
    """Test clear_databases when databases contain multiple entries."""
    # Mock multiple entries in databases
    mock_entries1 = [MagicMock(pk=f"pk1_{i}") for i in range(3)]
    mock_entries2 = [MagicMock(pk=f"pk2_{i}") for i in range(2)]
    mock_entries3 = [MagicMock(pk=f"pk3_{i}") for i in range(4)]
    
    cluster_manager.job_schema_targeting_database.all.return_value = mock_entries1
    cluster_manager.job_status_database.all.return_value = mock_entries2
    cluster_manager.worker_auto_connect_database.all.return_value = mock_entries3
    
    cluster_manager.clear_databases()
    
    # Verify all() was called on each database
    cluster_manager.job_schema_targeting_database.all.assert_called_once()
    cluster_manager.job_status_database.all.assert_called_once()
    cluster_manager.worker_auto_connect_database.all.assert_called_once()
    
    # Verify delete was called for each entry
    expected_calls1 = [((f"pk1_{i}",),) for i in range(3)]
    expected_calls2 = [((f"pk2_{i}",),) for i in range(2)]
    expected_calls3 = [((f"pk3_{i}",),) for i in range(4)]
    
    assert cluster_manager.job_schema_targeting_database.delete.call_args_list == expected_calls1
    assert cluster_manager.job_status_database.delete.call_args_list == expected_calls2
    assert cluster_manager.worker_auto_connect_database.delete.call_args_list == expected_calls3
    
    # Verify logging
    cluster_manager.logger.info.assert_called_once_with("Cleared all cluster manager databases")


def test_clear_databases_mixed_empty_and_populated(cluster_manager):
    """Test clear_databases when some databases are empty and others have entries."""
    # Mock mixed state: first database has entries, others are empty
    mock_entries = [MagicMock(pk="pk1"), MagicMock(pk="pk2")]
    
    cluster_manager.job_schema_targeting_database.all.return_value = mock_entries
    cluster_manager.job_status_database.all.return_value = []
    cluster_manager.worker_auto_connect_database.all.return_value = []
    
    cluster_manager.clear_databases()
    
    # Verify all() was called on each database
    cluster_manager.job_schema_targeting_database.all.assert_called_once()
    cluster_manager.job_status_database.all.assert_called_once()
    cluster_manager.worker_auto_connect_database.all.assert_called_once()
    
    # Verify delete was called only for entries in the first database
    cluster_manager.job_schema_targeting_database.delete.assert_any_call("pk1")
    cluster_manager.job_schema_targeting_database.delete.assert_any_call("pk2")
    assert cluster_manager.job_schema_targeting_database.delete.call_count == 2
    
    # Verify delete was not called for empty databases
    cluster_manager.job_status_database.delete.assert_not_called()
    cluster_manager.worker_auto_connect_database.delete.assert_not_called()
    
    # Verify logging
    cluster_manager.logger.info.assert_called_once_with("Cleared all cluster manager databases")


def test_clear_databases_database_error_handling(cluster_manager):
    """Test clear_databases when database operations raise exceptions."""
    # Mock database that raises an exception during all() call
    cluster_manager.job_schema_targeting_database.all.side_effect = Exception("Database connection error")
    cluster_manager.job_status_database.all.return_value = []
    cluster_manager.worker_auto_connect_database.all.return_value = []
    
    # Should raise the exception
    with pytest.raises(Exception, match="Database connection error"):
        cluster_manager.clear_databases()
    
    # Verify other databases were not processed due to the exception
    cluster_manager.job_status_database.all.assert_not_called()
    cluster_manager.worker_auto_connect_database.all.assert_not_called()


def test_clear_databases_delete_error_handling(cluster_manager):
    """Test clear_databases when delete operations raise exceptions."""
    # Mock entries and database that raises exception during delete
    mock_entry = MagicMock(pk="pk1")
    cluster_manager.job_schema_targeting_database.all.return_value = [mock_entry]
    cluster_manager.job_schema_targeting_database.delete.side_effect = Exception("Delete failed")
    cluster_manager.job_status_database.all.return_value = []
    cluster_manager.worker_auto_connect_database.all.return_value = []
    
    # Should raise the exception
    with pytest.raises(Exception, match="Delete failed"):
        cluster_manager.clear_databases()
    
    # Verify other databases were not processed due to the exception
    cluster_manager.job_status_database.all.assert_not_called()
    cluster_manager.worker_auto_connect_database.all.assert_not_called()


def test_clear_databases_logging_verification(cluster_manager):
    """Test that clear_databases logs the correct message."""
    # Mock empty databases
    cluster_manager.job_schema_targeting_database.all.return_value = []
    cluster_manager.job_status_database.all.return_value = []
    cluster_manager.worker_auto_connect_database.all.return_value = []
    
    cluster_manager.clear_databases()
    
    # Verify the exact log message
    cluster_manager.logger.info.assert_called_once_with("Cleared all cluster manager databases")


@pytest.fixture
def mock_node():
    """Create a mock node for testing."""
    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase, \
         patch("mindtrace.cluster.core.cluster.MinioRegistryBackend") as MockMinioBackend, \
         patch("mindtrace.cluster.core.cluster.Registry") as MockRegistry, \
         patch("mindtrace.cluster.core.cluster.ClusterManager.connect") as MockClusterManagerConnect:
        
        mock_database = MockDatabase.return_value
        mock_database.insert = MagicMock()
        mock_database.find = MagicMock(return_value=[])
        mock_database.delete = MagicMock()
        mock_database.redis_backend = MagicMock()
        mock_database.redis_backend.model_cls = MagicMock()
        
        mock_minio_backend = MockMinioBackend.return_value
        mock_registry = MockRegistry.return_value
        mock_cluster_manager_connect = MockClusterManagerConnect.return_value
        mock_cluster_manager_connect.worker_registry = mock_registry
        mock_cluster_manager_connect.worker_registry_endpoint = "http://localhost:8081"
        mock_cluster_manager_connect.worker_registry_access_key = "test_access_key"
        mock_cluster_manager_connect.worker_registry_secret_key = "test_secret_key"
        mock_cluster_manager_connect.worker_registry_bucket = "test_bucket"
        
        # Create Node with cluster_url
        node = Node(cluster_url="http://cluster:8080")
        node.id = uuid4()
        node.worker_registry = mock_registry
        object.__setattr__(node, "_url", "http://localhost:8081")
        
        return node


def test_node_initialization_with_cluster(mock_node):
    """Test Node initialization with cluster_url."""
    assert mock_node.cluster_url == "http://cluster:8080"
    assert mock_node.cluster_cm is not None
    assert mock_node.worker_registry is not None
    assert mock_node.workers == []


def test_node_initialization_without_cluster():
    """Test Node initialization without cluster_url."""
    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase:
        mock_database = MockDatabase.return_value
        mock_database.insert = MagicMock()
        mock_database.find = MagicMock(return_value=[])
        mock_database.delete = MagicMock()
        mock_database.redis_backend = MagicMock()
        mock_database.redis_backend.model_cls = MagicMock()
        
        node = Node()
        assert node.cluster_url is None
        assert node.cluster_cm is None
        assert node.worker_registry is None
        assert node.workers == []


def test_node_launch_worker(mock_node):
    """Test Node launch_worker method."""
    payload = {
        "worker_type": "test_worker",
        "worker_url": "http://worker:8080"
    }
    
    mock_worker = MagicMock()
    mock_worker.url = "http://worker:8080"
    mock_node.worker_registry.load.return_value = mock_worker
    
    result = mock_node.launch_worker(payload)
    
    assert result == "http://worker:8080"
    assert mock_worker in mock_node.workers
    mock_node.worker_registry.load.assert_called_once_with("worker:test_worker", url="http://worker:8080")


def test_node_shutdown(mock_node):
    """Test Node shutdown method."""
    # Add some mock workers
    mock_worker1 = MagicMock()
    mock_worker2 = MagicMock()
    mock_node.workers = [mock_worker1, mock_worker2]
    
    with patch.object(Service, 'shutdown') as mock_shutdown:
        result = mock_node.shutdown()
        
        # Verify all workers were shutdown
        mock_worker1.shutdown.assert_called_once()
        mock_worker2.shutdown.assert_called_once()
        # Verify super().shutdown() was called
        assert mock_shutdown.call_count == 1


def test_worker_initialization(mock_worker):
    """Test Worker initialization."""
    assert mock_worker.consume_process is None
    assert mock_worker._cluster_connection_manager is None
    assert mock_worker._cluster_url is None


def test_worker_cluster_connection_manager_property(mock_worker):
    """Test Worker cluster_connection_manager property."""
    # Initially should be None
    assert mock_worker.cluster_connection_manager is None
    
    # Set cluster URL
    mock_worker._cluster_url = "http://cluster:8080"
    
    with patch("mindtrace.cluster.core.cluster.ClusterManager") as MockClusterManager:
        mock_cm = MockClusterManager.connect.return_value
        mock_worker._cluster_connection_manager = None  # Reset to test property
        
        result = mock_worker.cluster_connection_manager
        
        assert result == mock_cm
        MockClusterManager.connect.assert_called_once_with("http://cluster:8080")


def test_worker_run_with_cluster_manager(mock_worker):
    """Test Worker run method with cluster manager."""
    job_dict = {
        "id": "job-123",
        "payload": {"test": "data"}
    }
    
    # Mock cluster connection manager
    mock_cm = MagicMock()
    mock_worker._cluster_connection_manager = mock_cm
    
    result = mock_worker.run(job_dict)
    
    # Verify cluster manager was called
    mock_cm.worker_alert_started_job.assert_called_once_with(job_id="job-123", worker_id=str(mock_worker.id))
    mock_cm.worker_alert_completed_job.assert_called_once_with(
        job_id="job-123", 
        worker_id=str(mock_worker.id), 
        status="completed", 
        output={"result": "test"}
    )
    assert result == {"status": "completed", "output": {"result": "test"}}


def test_worker_run_without_cluster_manager(mock_worker):
    """Test Worker run method without cluster manager."""
    job_dict = {
        "id": "job-123",
        "payload": {"test": "data"}
    }
    
    # Ensure no cluster connection manager
    mock_worker._cluster_connection_manager = None
    mock_worker._cluster_url = None
    
    with patch.object(mock_worker, 'logger') as mock_logger:
        result = mock_worker.run(job_dict)
        
        # Verify warning was logged
        assert mock_logger.warning.call_count == 2
        assert result == {"status": "completed", "output": {"result": "test"}}


def test_worker_start_method(mock_worker):
    """Test Worker start method."""
    # The start method should do nothing by default
    result = mock_worker.start()
    assert result is None


def test_worker_connect_to_cluster(mock_worker):
    """Test Worker connect_to_cluster method."""
    payload = {
        "backend_args": {"host": "localhost", "port": 5672},
        "queue_name": "test_queue",
        "cluster_url": "http://cluster:8080"
    }
    
    with patch.object(mock_worker, 'start') as mock_start, \
         patch.object(mock_worker, 'connect_to_orchestator_via_backend_args') as mock_connect_orchestrator, \
         patch.object(mock_worker, 'consume') as mock_consume, \
         patch('mindtrace.cluster.core.cluster.multiprocessing.Process') as MockProcess:
        
        mock_process = MockProcess.return_value
        mock_process.pid = 12345
        
        mock_worker.connect_to_cluster(payload)
        
        # Verify cluster URL was set
        assert mock_worker._cluster_url == "http://cluster:8080"
        
        # Verify methods were called
        mock_start.assert_called_once()
        mock_connect_orchestrator.assert_called_once_with(
            {"host": "localhost", "port": 5672}, 
            queue_name="test_queue"
        )
        
        # Verify process was started
        MockProcess.assert_called_once_with(target=mock_consume)
        mock_process.start.assert_called_once()
        
        # Verify consume process was stored
        assert mock_worker.consume_process == mock_process


def test_worker_shutdown_with_process(mock_worker):
    """Test Worker shutdown method with running process."""
    # Mock a running process
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_worker.consume_process = mock_process
    
    with patch.object(mock_worker, 'logger') as mock_logger, \
         patch.object(Service, 'shutdown') as mock_shutdown:
        
        result = mock_worker.shutdown()
        
        # Verify process was killed
        mock_process.kill.assert_called_once()
        mock_logger.info.assert_called_with(f"Worker {mock_worker.id} killed consume process 12345 as part of shutdown")
        
        # Verify super().shutdown() was called
        assert mock_shutdown.call_count == 1


def test_worker_shutdown_without_process(mock_worker):
    """Test Worker shutdown method without running process."""
    mock_worker.consume_process = None
    
    with patch.object(mock_worker, 'logger') as mock_logger, \
         patch.object(Service, 'shutdown') as mock_shutdown:
        
        result = mock_worker.shutdown()
        
        # Verify no process was killed
        mock_logger.info.assert_not_called()
        
        # Verify super().shutdown() was called
        assert mock_shutdown.call_count == 1


def test_worker_abstract_run_method():
    """Test that Worker abstract _run method raises NotImplementedError."""
    worker = Worker()
    
    with pytest.raises(NotImplementedError, match="Subclasses must implement this method"):
        worker._run({"test": "data"})


def test_worker_concrete_implementation():
    """Test that concrete Worker implementation works."""
    class ConcreteWorker(Worker):
        def _run(self, job_dict: dict) -> dict:
            return {"status": "completed", "output": {"result": "concrete"}}
    
    worker = ConcreteWorker()
    result = worker._run({"test": "data"})
    assert result == {"status": "completed", "output": {"result": "concrete"}}
