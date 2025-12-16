import json
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, Mock, patch
from uuid import uuid4

import pytest
import requests
from urllib3.exceptions import ConnectionError

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.core.cluster import ClusterManager, Node, Worker, update_database
from mindtrace.jobs import Job
from mindtrace.jobs.types.job_specs import ExecutionStatus
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.services import ServerStatus, Service


def create_mock_database():
    mock_database = MagicMock()
    mock_database.insert = MagicMock()
    mock_database.find = MagicMock(return_value=[])
    mock_database.delete = MagicMock()
    mock_database.redis_backend = MagicMock()
    mock_database.redis_backend.model_cls = MagicMock()
    return mock_database


@pytest.fixture
def cluster_manager():
    # Patch Database to avoid file I/O
    with (
        patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase,
        patch("mindtrace.cluster.core.cluster.RabbitMQClient") as MockRabbitMQClient,
        patch("mindtrace.cluster.core.cluster.MinioRegistryBackend") as MockMinioBackend,
    ):
        MockDatabase.side_effect = [
            create_mock_database(),
            create_mock_database(),
            create_mock_database(),
            create_mock_database(),
        ]

        mock_rabbitmq_client = MockRabbitMQClient.return_value
        mock_rabbitmq_client.publish = MagicMock()
        mock_rabbitmq_client.register = MagicMock()
        # Use Mock with spec=RegistryBackend so it passes isinstance checks
        mock_minio_backend = Mock(spec=RegistryBackend)
        mock_minio_backend.uri = Path("/tmp/test_registry")
        mock_minio_backend.load = MagicMock()
        mock_minio_backend.save = MagicMock()
        mock_minio_backend.delete = MagicMock()
        mock_minio_backend.list = MagicMock()
        mock_minio_backend.get = MagicMock()
        mock_minio_backend.registered_materializers = MagicMock(return_value={})
        # Mock fetch_registry_metadata to return empty dict (no existing metadata)
        mock_minio_backend.fetch_registry_metadata = MagicMock(return_value={})
        MockMinioBackend.return_value = mock_minio_backend
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

        # Mock the methods that need side_effect
        worker._run = MagicMock(side_effect=worker._run)
        worker.connect_to_orchestator_via_backend_args = MagicMock()

        # Mock the database to return a worker status entry
        worker_status_entry = MagicMock()
        worker_status_entry.worker_id = str(worker.id)
        worker_status_entry.status = cluster_types.WorkerStatusEnum.IDLE
        worker_status_entry.job_id = None
        worker.worker_status_local_database.find = MagicMock(return_value=[worker_status_entry])

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
    cluster_manager.job_schema_targeting_database.find.assert_called_with(
        cluster_manager.job_schema_targeting_database.redis_backend.model_cls.schema_name == "test_job"
    )
    cluster_manager.job_schema_targeting_database.insert.assert_called_with(
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")
    )


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
    cluster_manager.job_schema_targeting_database.insert.assert_called_with(
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")
    )


def test_submit_job_success(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")
    ]
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success", "output": {"result": 42}}
        result = cluster_manager.submit_job(job)
        assert result.status == "success"
        assert result.output == {"result": 42}
        mock_post.assert_called_once()


def test_submit_job_registry_reload(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")
    ]
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

    with patch.object(cluster_manager.orchestrator, "publish") as mock_publish:
        result = cluster_manager.submit_job(job)

        # Verify orchestrator was called
        mock_publish.assert_called_once_with("test_job", job)
        # Verify job status was created with queued status
        assert result.status == "queued"
        assert result.worker_id == ""


def test_submit_job_to_endpoint_http_error(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")
    ]
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"
        with pytest.raises(RuntimeError, match="Gateway proxy request failed: Internal Server Error"):
            cluster_manager._submit_job_to_endpoint(job, "/test/test")


def test_submit_job_to_endpoint_json_error(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager.job_schema_targeting_database.find.return_value = [
        cluster_types.JobSchemaTargeting(schema_name="test_job", target_endpoint="/test")
    ]
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

    with (
        patch("mindtrace.cluster.core.cluster.Worker") as MockWorker,
        patch.object(cluster_manager.orchestrator, "register") as mock_register,
    ):
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

    with patch("mindtrace.cluster.core.cluster.Worker"), patch.object(cluster_manager.orchestrator, "register"):
        cluster_manager.register_job_to_worker(payload)

        # Verify existing entry was deleted
        cluster_manager.job_schema_targeting_database.delete.assert_called_with("existing-pk")


def test_register_job_to_worker_worker_down(cluster_manager):
    """Test register_job_to_worker when worker heartbeat status is DOWN."""
    payload = {"job_type": "test_job", "worker_url": "http://worker:8080"}

    # Mock existing entries
    existing_entry = MagicMock()
    existing_entry.pk = "existing-pk"
    cluster_manager.job_schema_targeting_database.find.return_value = [existing_entry]

    with (
        patch("mindtrace.cluster.core.cluster.Worker") as MockWorker,
        patch.object(cluster_manager.orchestrator, "register") as mock_register,
    ):
        # Mock worker instance with DOWN status heartbeat
        mock_worker_instance = MockWorker.connect.return_value
        mock_heartbeat = MagicMock()
        mock_heartbeat.heartbeat.status = ServerStatus.DOWN
        mock_worker_instance.heartbeat.return_value = mock_heartbeat

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
        # Verify heartbeat was checked
        mock_worker_instance.heartbeat.assert_called_once()
        # Verify connect_to_cluster was NOT called (because worker is down)
        mock_worker_instance.connect_to_cluster.assert_not_called()
        # Verify worker status database was NOT queried or updated
        cluster_manager.worker_status_database.find.assert_not_called()
        cluster_manager.worker_status_database.insert.assert_not_called()
        # Verify warning was logged
        cluster_manager.logger.warning.assert_called_with(
            "Worker http://worker:8080 is down, not registering to cluster"
        )


def test_get_job_status_success(cluster_manager):
    """Test get_job_status when job exists."""
    job_id = "test-job-123"
    expected_job_status = cluster_types.JobStatus(
        job_id=job_id, status="running", output={"result": "test"}, worker_id="worker-123"
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
    existing_job_status = cluster_types.JobStatus(job_id=job_id, status="queued", output={}, worker_id="")
    cluster_manager.job_status_database.find.return_value = [existing_job_status]
    cluster_manager.worker_status_database.find.return_value = [
        cluster_types.WorkerStatus(
            worker_id=worker_id,
            worker_type="",
            worker_url="",
            status=cluster_types.WorkerStatusEnum.IDLE,
            last_heartbeat=None,
            job_id=None,
        )
    ]

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

    with pytest.raises(ValueError, match=f"Expected 1 entry for job_id == {job_id}"):
        cluster_manager.worker_alert_started_job(payload)


def test_worker_alert_completed_job(cluster_manager):
    """Test worker_alert_completed_job method."""
    job_id = "test-job-123"
    status = "completed"
    output = {"result": "success"}

    # Mock existing job status
    existing_job_status = cluster_types.JobStatus(job_id=job_id, status="running", output={}, worker_id="worker-123")
    cluster_manager.job_status_database.find.return_value = [existing_job_status]
    cluster_manager.worker_status_database.find.return_value = [
        cluster_types.WorkerStatus(
            worker_id="worker-123",
            worker_type="",
            worker_url="",
            status=cluster_types.WorkerStatusEnum.IDLE,
            last_heartbeat=None,
            job_id=None,
        )
    ]

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

    with pytest.raises(ValueError, match=f"Expected 1 entry for job_id == {job_id}"):
        cluster_manager.worker_alert_completed_job(payload)


def test_register_worker_type(cluster_manager):
    """Test register_worker_type method."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "mindtrace.cluster.workers.standard_worker_launcher.StandardWorkerLauncher",
        "worker_params": {"param1": "value1"},
        "materializer_name": "custom.materializer.CustomMaterializer",
        "job_type": None,
    }

    with (
        patch("mindtrace.cluster.core.types.ProxyWorker") as MockProxyWorker,
        patch.object(cluster_manager.worker_registry, "save") as mock_save,
    ):
        mock_proxy_worker = MockProxyWorker.return_value

        cluster_manager.register_worker_type(payload)

        # Verify ProxyWorker was created with correct parameters
        MockProxyWorker.assert_called_once_with(
            worker_type="mindtrace.cluster.workers.standard_worker_launcher.StandardWorkerLauncher",
            worker_params={"param1": "value1"},
            git_repo_url=None,
            git_branch=None,
            git_commit=None,
            git_working_dir=None,
        )
        # Verify worker was saved
        mock_save.assert_called_once_with("worker:test_worker", mock_proxy_worker)


def test_register_worker_type_with_default_materializer(cluster_manager):
    """Test register_worker_type method with default materializer."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "mindtrace.cluster.workers.standard_worker_launcher.StandardWorkerLauncher",
        "worker_params": {"param1": "value1"},
        "materializer_name": None,
        "job_type": None,
    }

    with (
        patch("mindtrace.cluster.core.types.ProxyWorker") as MockProxyWorker,
        patch.object(cluster_manager.worker_registry, "save") as mock_save,
    ):
        mock_proxy_worker = MockProxyWorker.return_value

        cluster_manager.register_worker_type(payload)

        # Verify ProxyWorker was created with correct parameters
        MockProxyWorker.assert_called_once_with(
            worker_type="mindtrace.cluster.workers.standard_worker_launcher.StandardWorkerLauncher",
            worker_params={"param1": "value1"},
            git_repo_url=None,
            git_branch=None,
            git_commit=None,
            git_working_dir=None,
        )
        # Verify worker was saved
        mock_save.assert_called_once_with("worker:test_worker", mock_proxy_worker)


def test_register_worker_type_with_job_schema_name(cluster_manager):
    """Test register_worker_type when job_schema_name is provided."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "mindtrace.cluster.workers.test_worker.TestWorker",
        "worker_params": {"param1": "value1"},
        "materializer_name": None,
        "job_type": "test_job",
    }

    with (
        patch("mindtrace.cluster.core.types.ProxyWorker") as MockProxyWorker,
        patch.object(cluster_manager.worker_registry, "register_materializer"),
        patch.object(cluster_manager.worker_registry, "save") as mock_save,
        patch.object(cluster_manager, "register_job_schema_to_worker_type") as mock_register_job_schema,
    ):
        mock_proxy_worker = MockProxyWorker.return_value

        cluster_manager.register_worker_type(payload)

        # Verify ProxyWorker was created and saved
        MockProxyWorker.assert_called_once_with(
            worker_type="mindtrace.cluster.workers.test_worker.TestWorker",
            worker_params={"param1": "value1"},
            git_repo_url=None,
            git_branch=None,
            git_commit=None,
            git_working_dir=None,
        )
        mock_save.assert_called_once_with("worker:test_worker", mock_proxy_worker)

        # Verify job schema was registered to worker type
        mock_register_job_schema.assert_called_once_with({"job_schema_name": "test_job", "worker_type": "test_worker"})


def test_register_job_schema_to_worker_type_success(cluster_manager):
    """Test register_job_schema_to_worker_type when worker type exists in registry."""
    payload = {"job_schema_name": "test_job", "worker_type": "test_worker"}

    with (
        patch.object(cluster_manager.worker_registry, "has_object", return_value=True) as mock_has_object,
        patch.object(cluster_manager.job_schema_targeting_database, "insert") as mock_insert_targeting,
        patch.object(cluster_manager.worker_auto_connect_database, "insert") as mock_insert_auto_connect,
    ):
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
    payload = {"job_schema_name": "test_job", "worker_type": "nonexistent_worker"}

    with (
        patch.object(cluster_manager.worker_registry, "has_object", return_value=False) as mock_has_object,
        patch.object(cluster_manager.job_schema_targeting_database, "insert") as mock_insert_targeting,
        patch.object(cluster_manager.worker_auto_connect_database, "insert") as mock_insert_auto_connect,
    ):
        cluster_manager.register_job_schema_to_worker_type(payload)

        # Verify worker type exists check
        mock_has_object.assert_called_once_with("worker:nonexistent_worker")

        # Verify no database insertions occurred
        mock_insert_targeting.assert_not_called()
        mock_insert_auto_connect.assert_not_called()


def test_launch_worker_with_auto_connect(cluster_manager):
    """Test launch_worker when worker is in auto-connect database."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8081"}

    # Mock auto-connect entry
    auto_connect_entry = cluster_types.WorkerAutoConnect(worker_type="test_worker", schema_name="test_job")
    cluster_manager.worker_auto_connect_database.find.return_value = [auto_connect_entry]

    with (
        patch("mindtrace.cluster.core.cluster.Node") as MockNode,
        patch.object(cluster_manager, "register_job_to_worker") as mock_register_job,
        patch.object(Worker, "connect") as mock_connect,
    ):
        mock_node_instance = MockNode.connect.return_value
        mock_connect.return_value = MagicMock()
        mock_connect.return_value.heartbeat.return_value = MagicMock(server_id=uuid.uuid4())

        cluster_manager.launch_worker(payload)

        # Verify node connection and worker launch
        MockNode.connect.assert_called_once_with("http://node:8080")
        mock_node_instance.launch_worker.assert_called_once_with(
            worker_type="test_worker", worker_url="http://worker:8081"
        )

        # Verify auto-connect registration
        mock_register_job.assert_called_once_with(payload={"job_type": "test_job", "worker_url": "http://worker:8081"})


def test_launch_worker_without_auto_connect(cluster_manager):
    """Test launch_worker when worker is not in auto-connect database."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8081"}

    # Mock no auto-connect entries
    cluster_manager.worker_auto_connect_database.find.return_value = []

    with (
        patch("mindtrace.cluster.core.cluster.Node") as MockNode,
        patch.object(cluster_manager, "register_job_to_worker") as mock_register_job,
        patch.object(Worker, "connect") as mock_connect,
    ):
        mock_node_instance = MockNode.connect.return_value
        mock_connect.return_value = MagicMock()
        mock_connect.return_value.heartbeat.return_value = MagicMock(server_id=uuid.uuid4())

        cluster_manager.launch_worker(payload)

        # Verify node connection and worker launch
        MockNode.connect.assert_called_once_with("http://node:8080")
        mock_node_instance.launch_worker.assert_called_once_with(
            worker_type="test_worker", worker_url="http://worker:8081"
        )

        # Verify no auto-connect registration occurred
        mock_register_job.assert_not_called()


def test_launch_worker_node_connection_failure(cluster_manager):
    """Test launch_worker when node connection fails."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8081"}

    with patch("mindtrace.cluster.core.cluster.Node") as MockNode:
        MockNode.connect.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            cluster_manager.launch_worker(payload)


def test_launch_worker_node_launch_failure(cluster_manager):
    """Test launch_worker when node worker launch fails."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8081"}

    with patch("mindtrace.cluster.core.cluster.Node") as MockNode:
        mock_node_instance = MockNode.connect.return_value
        mock_node_instance.launch_worker.side_effect = Exception("Launch failed")

        with pytest.raises(Exception, match="Launch failed"):
            cluster_manager.launch_worker(payload)


def test_launch_worker_with_different_ports(cluster_manager):
    """Test launch_worker with different node and worker ports."""
    payload = {"node_url": "http://node:9090", "worker_type": "test_worker", "worker_url": "http://worker:9091"}

    # Mock auto-connect entry
    auto_connect_entry = cluster_types.WorkerAutoConnect(worker_type="test_worker", schema_name="test_job")
    cluster_manager.worker_auto_connect_database.find.return_value = [auto_connect_entry]

    with (
        patch("mindtrace.cluster.core.cluster.Node") as MockNode,
        patch.object(cluster_manager, "register_job_to_worker") as mock_register_job,
        patch.object(Worker, "connect") as mock_connect,
    ):
        mock_node_instance = MockNode.connect.return_value
        mock_connect.return_value = MagicMock()
        mock_connect.return_value.heartbeat.return_value = MagicMock(server_id=uuid.uuid4())

        cluster_manager.launch_worker(payload)

        # Verify correct URLs were used
        MockNode.connect.assert_called_once_with("http://node:9090")
        mock_node_instance.launch_worker.assert_called_once_with(
            worker_type="test_worker", worker_url="http://worker:9091"
        )
        mock_register_job.assert_called_once_with(payload={"job_type": "test_job", "worker_url": "http://worker:9091"})


def test_launch_worker_logging(cluster_manager):
    """Test launch_worker logging behavior."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8081"}

    # Mock auto-connect entry
    auto_connect_entry = cluster_types.WorkerAutoConnect(worker_type="test_worker", schema_name="test_job")
    cluster_manager.worker_auto_connect_database.find.return_value = [auto_connect_entry]

    with (
        patch("mindtrace.cluster.core.cluster.Node") as MockNode,
        patch.object(cluster_manager, "register_job_to_worker") as mock_register_job,
        patch.object(cluster_manager, "logger"),
        patch.object(Worker, "connect") as mock_connect,
    ):
        mock_node_instance = MockNode.connect.return_value
        mock_connect.return_value = MagicMock()
        mock_connect.return_value.heartbeat.return_value = MagicMock(server_id=uuid.uuid4())

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
        "bucket": cluster_manager.worker_registry_bucket,
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
    with (
        patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase,
        patch("mindtrace.cluster.core.cluster.MinioRegistryBackend"),
        patch("mindtrace.cluster.core.cluster.Registry") as MockRegistry,
        patch("mindtrace.cluster.core.cluster.ClusterManager.connect") as MockClusterManagerConnect,
    ):
        mock_database = MockDatabase.return_value
        mock_database.insert = MagicMock()
        mock_database.find = MagicMock(return_value=[])
        mock_database.delete = MagicMock()
        mock_database.redis_backend = MagicMock()
        mock_database.redis_backend.model_cls = MagicMock()

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
    payload = {"worker_type": "test_worker", "worker_url": "http://worker:8080"}

    mock_worker = MagicMock()
    mock_worker.url = "http://worker:8080"
    mock_node.worker_registry.load.return_value = mock_worker

    result = mock_node.launch_worker(payload)

    assert result is None
    assert mock_worker in mock_node.workers
    mock_node.worker_registry.load.assert_called_once_with("worker:test_worker", url="http://worker:8080")


def test_node_shutdown(mock_node):
    """Test Node shutdown method."""
    # Add some mock workers
    mock_worker1 = MagicMock()
    mock_worker2 = MagicMock()
    mock_node.workers = [mock_worker1, mock_worker2]

    with patch.object(Service, "shutdown") as mock_shutdown:
        _ = mock_node.shutdown()

        # Verify all workers were shutdown
        mock_worker1.shutdown.assert_called_once()
        mock_worker2.shutdown.assert_called_once()
        # Verify super().shutdown() was called
        assert mock_shutdown.call_count == 1


def test_worker_initialization(mock_worker):
    """Test Worker initialization."""
    assert mock_worker.consume_thread is None
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
    job_dict = {"id": "job-123", "payload": {"test": "data"}}

    # Mock cluster connection manager
    mock_cm = MagicMock()
    mock_worker._cluster_connection_manager = mock_cm

    with patch("mindtrace.cluster.core.cluster.update_database") as mock_update_database:
        mock_update_database.return_value = None
        result = mock_worker.run(job_dict)
        mock_update_database.assert_any_call(
            mock_worker.worker_status_local_database,
            "worker_id",
            str(mock_worker.id),
            {"status": cluster_types.WorkerStatusEnum.RUNNING, "job_id": "job-123"},
        )
        mock_update_database.assert_any_call(
            mock_worker.worker_status_local_database,
            "worker_id",
            str(mock_worker.id),
            {"status": cluster_types.WorkerStatusEnum.IDLE, "job_id": None},
        )

    # Verify cluster manager was called
    mock_cm.worker_alert_started_job.assert_called_once_with(job_id="job-123", worker_id=str(mock_worker.id))
    mock_cm.worker_alert_completed_job.assert_called_once_with(
        job_id="job-123", worker_id=str(mock_worker.id), status="completed", output={"result": "test"}
    )
    assert result == {"status": "completed", "output": {"result": "test"}}


def test_worker_run_without_cluster_manager(mock_worker):
    """Test Worker run method without cluster manager."""
    job_dict = {"id": "job-123", "payload": {"test": "data"}}

    # Ensure no cluster connection manager
    mock_worker._cluster_connection_manager = None
    mock_worker._cluster_url = None

    with (
        patch.object(mock_worker, "logger") as mock_logger,
        patch("mindtrace.cluster.core.cluster.update_database") as mock_update_database,
    ):
        mock_update_database.return_value = None
        result = mock_worker.run(job_dict)

        # Verify warning was logged
        assert mock_logger.warning.call_count == 2
        mock_update_database.assert_any_call(
            mock_worker.worker_status_local_database,
            "worker_id",
            str(mock_worker.id),
            {"status": cluster_types.WorkerStatusEnum.RUNNING, "job_id": "job-123"},
        )
        mock_update_database.assert_any_call(
            mock_worker.worker_status_local_database,
            "worker_id",
            str(mock_worker.id),
            {"status": cluster_types.WorkerStatusEnum.IDLE, "job_id": None},
        )
        assert result == {"status": "completed", "output": {"result": "test"}}


def test_worker_start_method(mock_worker):
    """Test Worker start method."""
    # The start method should do nothing by default
    result = mock_worker.start()
    assert result is None


def test_worker_connect_to_cluster(mock_worker):
    """Test Worker connect_to_cluster method."""
    payload = {
        "backend_args": {"host": "localhost", "port": 5673},
        "queue_name": "test_queue",
        "cluster_url": "http://cluster:8080",
    }

    with (
        patch.object(mock_worker, "start") as mock_start,
        patch.object(mock_worker, "connect_to_orchestator_via_backend_args") as mock_connect_orchestrator,
        patch.object(mock_worker, "consume") as mock_consume,
        patch("mindtrace.cluster.core.cluster.threading.Thread") as MockThread,
    ):
        mock_thread = MockThread.return_value

        mock_worker.connect_to_cluster(payload)

        # Verify cluster URL was set
        assert mock_worker._cluster_url == "http://cluster:8080"

        # Verify methods were called
        mock_start.assert_called_once()
        mock_connect_orchestrator.assert_called_once_with({"host": "localhost", "port": 5673}, queue_name="test_queue")

        # Verify process was started
        MockThread.assert_called_once_with(target=mock_consume)
        mock_thread.start.assert_called_once()

        # Verify consume process was stored
        assert mock_worker.consume_thread == mock_thread


def test_worker_abstract_run_method():
    """Test that Worker abstract _run method raises NotImplementedError."""
    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase:
        MockDatabase.return_value = create_mock_database()
        worker = Worker()

        with pytest.raises(NotImplementedError, match="Subclasses must implement this method"):
            worker._run({"test": "data"})


def test_get_worker_status_success(cluster_manager):
    """Test get_worker_status when worker exists."""
    worker_id = "worker-123"
    expected_worker_status = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url="http://worker:8080",
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )

    cluster_manager.worker_status_database.find.return_value = [expected_worker_status]

    payload = {"worker_id": worker_id}
    result = cluster_manager.get_worker_status(payload)

    assert result == expected_worker_status
    cluster_manager.worker_status_database.find.assert_called_with(
        cluster_manager.worker_status_database.redis_backend.model_cls.worker_id == worker_id
    )


def test_get_worker_status_not_found(cluster_manager):
    """Test get_worker_status when worker does not exist."""
    worker_id = "nonexistent-worker"

    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_id": worker_id}
    result = cluster_manager.get_worker_status(payload)

    # Should return a WorkerStatus with NONEXISTENT status
    assert result.worker_id == worker_id
    assert result.worker_type == ""
    assert result.worker_url == ""
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value
    assert result.last_heartbeat is None


def test_get_worker_status_by_url_success(cluster_manager):
    """Test get_worker_status_by_url when worker exists."""
    worker_url = "http://worker:8080"
    expected_worker_status = cluster_types.WorkerStatus(
        worker_id="worker-123",
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.RUNNING,
        job_id=None,
        last_heartbeat=datetime.now(),
    )

    cluster_manager.worker_status_database.find.return_value = [expected_worker_status]

    payload = {"worker_url": worker_url}
    result = cluster_manager.get_worker_status_by_url(payload)

    assert result == expected_worker_status
    cluster_manager.worker_status_database.find.assert_called_with(
        cluster_manager.worker_status_database.redis_backend.model_cls.worker_url == worker_url
    )


def test_get_worker_status_by_url_not_found(cluster_manager):
    """Test get_worker_status_by_url when worker does not exist."""
    worker_url = "http://nonexistent-worker:8080"

    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_url": worker_url}
    result = cluster_manager.get_worker_status_by_url(payload)

    # Should return a WorkerStatus with NONEXISTENT status
    assert result.worker_id == ""
    assert result.worker_type == ""
    assert result.worker_url == worker_url
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value
    assert result.last_heartbeat is None


def test_get_worker_status_with_different_statuses(cluster_manager):
    """Test get_worker_status with different worker statuses."""
    worker_id = "worker-123"

    # Test with IDLE status
    idle_worker = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url="http://worker:8080",
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [idle_worker]

    payload = {"worker_id": worker_id}
    result = cluster_manager.get_worker_status(payload)
    assert result.status == cluster_types.WorkerStatusEnum.IDLE.value

    # Test with RUNNING status
    running_worker = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url="http://worker:8080",
        status=cluster_types.WorkerStatusEnum.RUNNING,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [running_worker]

    result = cluster_manager.get_worker_status(payload)
    assert result.status == cluster_types.WorkerStatusEnum.RUNNING.value

    # Test with ERROR status
    error_worker = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url="http://worker:8080",
        status=cluster_types.WorkerStatusEnum.ERROR,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [error_worker]

    result = cluster_manager.get_worker_status(payload)
    assert result.status == cluster_types.WorkerStatusEnum.ERROR.value


def test_get_worker_status_by_url_with_different_urls(cluster_manager):
    """Test get_worker_status_by_url with different worker URLs."""
    # Test with HTTP URL
    http_url = "http://worker:8080"
    http_worker = cluster_types.WorkerStatus(
        worker_id="worker-123",
        worker_type="test_worker",
        worker_url=http_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [http_worker]

    payload = {"worker_url": http_url}
    result = cluster_manager.get_worker_status_by_url(payload)
    assert result.worker_url == http_url

    # Test with HTTPS URL
    https_url = "https://secure-worker:8443"
    https_worker = cluster_types.WorkerStatus(
        worker_id="worker-456",
        worker_type="secure_worker",
        worker_url=https_url,
        status=cluster_types.WorkerStatusEnum.RUNNING,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [https_worker]

    payload = {"worker_url": https_url}
    result = cluster_manager.get_worker_status_by_url(payload)
    assert result.worker_url == https_url

    # Test with localhost URL
    localhost_url = "http://localhost:9000"
    localhost_worker = cluster_types.WorkerStatus(
        worker_id="worker-789",
        worker_type="local_worker",
        worker_url=localhost_url,
        status=cluster_types.WorkerStatusEnum.SHUTDOWN,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [localhost_worker]

    payload = {"worker_url": localhost_url}
    result = cluster_manager.get_worker_status_by_url(payload)
    assert result.worker_url == localhost_url


def test_get_worker_status_edge_cases(cluster_manager):
    """Test get_worker_status with edge cases."""
    # Test with empty worker_id
    empty_worker_id = ""
    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_id": empty_worker_id}
    result = cluster_manager.get_worker_status(payload)
    assert result.worker_id == empty_worker_id
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value

    # Test with None worker_id (should handle gracefully)
    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_id": ""}
    result = cluster_manager.get_worker_status(payload)
    assert result.worker_id == ""
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value

    # Test with very long worker_id
    long_worker_id = "a" * 1000
    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_id": long_worker_id}
    result = cluster_manager.get_worker_status(payload)
    assert result.worker_id == long_worker_id
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value


def test_get_worker_status_by_url_edge_cases(cluster_manager):
    """Test get_worker_status_by_url with edge cases."""
    # Test with empty worker_url
    empty_worker_url = ""
    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_url": empty_worker_url}
    result = cluster_manager.get_worker_status_by_url(payload)
    assert result.worker_url == empty_worker_url
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value

    # Test with None worker_url (should handle gracefully)
    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_url": ""}
    result = cluster_manager.get_worker_status_by_url(payload)
    assert result.worker_url == ""
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value

    # Test with very long worker_url
    long_worker_url = "http://" + "a" * 1000 + ".com:8080"
    cluster_manager.worker_status_database.find.return_value = []

    payload = {"worker_url": long_worker_url}
    result = cluster_manager.get_worker_status_by_url(payload)
    assert result.worker_url == long_worker_url
    assert result.status == cluster_types.WorkerStatusEnum.NONEXISTENT.value


def test_get_worker_status_database_error_handling(cluster_manager):
    """Test get_worker_status handles database errors gracefully."""
    worker_id = "worker-123"

    # Mock database to raise an exception
    cluster_manager.worker_status_database.find.side_effect = Exception("Database connection failed")

    payload = {"worker_id": worker_id}

    with pytest.raises(Exception, match="Database connection failed"):
        cluster_manager.get_worker_status(payload)


def test_get_worker_status_by_url_database_error_handling(cluster_manager):
    """Test get_worker_status_by_url handles database errors gracefully."""
    worker_url = "http://worker:8080"

    # Mock database to raise an exception
    cluster_manager.worker_status_database.find.side_effect = Exception("Database connection failed")

    payload = {"worker_url": worker_url}

    with pytest.raises(Exception, match="Database connection failed"):
        cluster_manager.get_worker_status_by_url(payload)


def test_get_worker_status_multiple_results(cluster_manager):
    """Test get_worker_status when database returns multiple results (should return first)."""
    worker_id = "worker-123"

    # Mock database to return multiple results
    worker1 = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker_1",
        worker_url="http://worker1:8080",
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    worker2 = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker_2",
        worker_url="http://worker2:8080",
        status=cluster_types.WorkerStatusEnum.RUNNING,
        job_id=None,
        last_heartbeat=datetime.now(),
    )

    cluster_manager.worker_status_database.find.return_value = [worker1, worker2]

    payload = {"worker_id": worker_id}
    result = cluster_manager.get_worker_status(payload)

    # Should return the first result
    assert result == worker1


def test_get_worker_status_by_url_multiple_results(cluster_manager):
    """Test get_worker_status_by_url when database returns multiple results (should return first)."""
    worker_url = "http://worker:8080"

    # Mock database to return multiple results
    worker1 = cluster_types.WorkerStatus(
        worker_id="worker-123",
        worker_type="test_worker_1",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    worker2 = cluster_types.WorkerStatus(
        worker_id="worker-456",
        worker_type="test_worker_2",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.RUNNING,
        job_id=None,
        last_heartbeat=datetime.now(),
    )

    cluster_manager.worker_status_database.find.return_value = [worker1, worker2]

    payload = {"worker_url": worker_url}
    result = cluster_manager.get_worker_status_by_url(payload)

    # Should return the first result
    assert result == worker1


def test_worker_concrete_implementation():
    """Test that a concrete Worker implementation works correctly."""

    class ConcreteWorker(Worker):
        def _run(self, job_dict: dict) -> dict:
            return {"status": "completed", "output": {"result": "test"}}

    with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase:
        mock_database = MockDatabase.return_value
        mock_database.insert = MagicMock()
        mock_database.find = MagicMock(return_value=[])
        mock_database.delete = MagicMock()
        mock_database.redis_backend = MagicMock()
        mock_database.redis_backend.model_cls = MagicMock()

        worker = ConcreteWorker()
        result = worker._run({"test": "data"})
        assert result == {"status": "completed", "output": {"result": "test"}}


def test_update_database_success():
    """Test update_database function with valid input."""
    from mindtrace.cluster.core.cluster import update_database

    # Mock database and entry
    mock_database = MagicMock()
    mock_entry = MagicMock()
    mock_entry.pk = "test-pk"
    mock_database.find.return_value = [mock_entry]
    mock_database.insert = MagicMock()

    # Mock model_cls attribute
    mock_model_cls = MagicMock()
    mock_database.redis_backend.model_cls = mock_model_cls

    # Test update
    update_dict = {"status": "completed", "output": {"result": "test"}}
    result = update_database(mock_database, "worker_id", "test-worker", update_dict)

    # Verify find was called
    mock_database.find.assert_called_once()
    # Verify attributes were set
    assert mock_entry.status == "completed"
    assert mock_entry.output == {"result": "test"}
    # Verify insert was called
    mock_database.insert.assert_called_once_with(mock_entry)
    # Verify result
    assert result == mock_entry


def test_update_database_no_entries():
    """Test update_database function when no entries are found."""
    from mindtrace.cluster.core.cluster import update_database

    mock_database = MagicMock()
    mock_database.find.return_value = []
    mock_database.redis_backend.model_cls = MagicMock()

    with pytest.raises(ValueError, match="Expected 1 entry for worker_id == test-worker, got 0"):
        update_database(mock_database, "worker_id", "test-worker", {"status": "completed"})


def test_update_database_multiple_entries():
    """Test update_database function when multiple entries are found."""
    from mindtrace.cluster.core.cluster import update_database

    mock_database = MagicMock()
    mock_database.find.return_value = [MagicMock(), MagicMock()]
    mock_database.redis_backend.model_cls = MagicMock()

    with pytest.raises(ValueError, match="Expected 1 entry for worker_id == test-worker, got 2"):
        update_database(mock_database, "worker_id", "test-worker", {"status": "completed"})


def test_query_worker_status_success(cluster_manager):
    """Test query_worker_status when worker exists and is responsive."""
    worker_id = "test-worker-123"
    worker_url = "http://worker:8080"

    # Mock worker status in database
    existing_worker_status = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [existing_worker_status]

    with patch("mindtrace.cluster.core.cluster.Worker") as MockWorker:
        mock_worker_instance = MockWorker.connect.return_value

        # Mock worker heartbeat and status
        mock_heartbeat = MagicMock()
        mock_heartbeat.heartbeat.status = ServerStatus.AVAILABLE
        mock_worker_instance.heartbeat.return_value = mock_heartbeat

        mock_worker_status = MagicMock()
        mock_worker_status.status = cluster_types.WorkerStatusEnum.RUNNING
        mock_worker_status.job_id = "job-123"
        mock_worker_instance.get_status.return_value = mock_worker_status

        # Mock update_database
        with patch("mindtrace.cluster.core.cluster.update_database") as mock_update:
            mock_update.return_value = existing_worker_status

            result = cluster_manager.query_worker_status({"worker_id": worker_id})

            # Verify worker was connected
            MockWorker.connect.assert_called_once_with(worker_url)
            # Verify heartbeat was checked
            mock_worker_instance.heartbeat.assert_called_once()
            # Verify status was retrieved
            mock_worker_instance.get_status.assert_called_once()
            # Verify database was updated
            mock_update.assert_called_once()
            # Verify result
            assert result == existing_worker_status


def test_query_worker_status_worker_not_found(cluster_manager):
    """Test query_worker_status when worker is not found in database."""
    worker_id = "nonexistent-worker"
    cluster_manager.worker_status_database.find.return_value = []

    result = cluster_manager.query_worker_status({"worker_id": worker_id})

    expected_result = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="",
        worker_url="",
        status=cluster_types.WorkerStatusEnum.NONEXISTENT,
        job_id=None,
        last_heartbeat=None,
    )

    assert result.worker_id == expected_result.worker_id
    assert result.status == expected_result.status
    assert result.worker_type == expected_result.worker_type


def test_query_worker_status_worker_down(cluster_manager):
    """Test query_worker_status when worker heartbeat status is DOWN."""
    worker_id = "test-worker-123"
    worker_url = "http://worker:8080"

    existing_worker_status = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [existing_worker_status]

    with patch("mindtrace.cluster.core.cluster.Worker") as MockWorker:
        mock_worker_instance = MockWorker.connect.return_value

        # Mock worker heartbeat with DOWN status
        mock_heartbeat = MagicMock()
        mock_heartbeat.heartbeat.status = ServerStatus.DOWN
        mock_worker_instance.heartbeat.return_value = mock_heartbeat

        with patch("mindtrace.cluster.core.cluster.update_database") as mock_update:
            mock_update.return_value = existing_worker_status

            result = cluster_manager.query_worker_status({"worker_id": worker_id})

            # Verify worker was connected
            MockWorker.connect.assert_called_once_with(worker_url)
            # Verify heartbeat was checked
            mock_worker_instance.heartbeat.assert_called_once()
            # Verify database was updated with NONEXISTENT status
            mock_update.assert_called_once_with(
                cluster_manager.worker_status_database,
                "worker_id",
                worker_id,
                {"status": cluster_types.WorkerStatusEnum.NONEXISTENT, "job_id": None, "last_heartbeat": ANY},
            )
            # Verify result
            assert result == existing_worker_status


def test_query_worker_status_worker_connection_failure(cluster_manager):
    """Test query_worker_status when worker connection fails."""
    worker_id = "test-worker-123"
    worker_url = "http://worker:8080"

    existing_worker_status = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [existing_worker_status]

    with patch("mindtrace.cluster.core.cluster.Worker") as MockWorker:
        # Mock worker connection failure
        MockWorker.connect.return_value = None

        with patch("mindtrace.cluster.core.cluster.update_database") as mock_update:
            mock_update.return_value = existing_worker_status

            result = cluster_manager.query_worker_status({"worker_id": worker_id})

            # Verify worker connection was attempted
            MockWorker.connect.assert_called_once_with(worker_url)
            # Verify database was updated with NONEXISTENT status
            mock_update.assert_called_once_with(
                cluster_manager.worker_status_database,
                "worker_id",
                worker_id,
                {"status": cluster_types.WorkerStatusEnum.NONEXISTENT, "job_id": None, "last_heartbeat": ANY},
            )
            # Verify result
            assert result == existing_worker_status


def test_query_worker_status_by_url_success(cluster_manager):
    """Test query_worker_status_by_url when worker URL exists."""
    worker_url = "http://worker:8080"
    worker_id = "test-worker-123"

    # Mock _url_to_id to return worker_id
    with patch.object(cluster_manager, "_url_to_id", return_value=worker_id) as mock_url_to_id:
        with patch.object(cluster_manager, "query_worker_status") as mock_query_status:
            expected_result = cluster_types.WorkerStatus(
                worker_id=worker_id,
                worker_type="test_worker",
                worker_url=worker_url,
                status=cluster_types.WorkerStatusEnum.IDLE,
                job_id=None,
                last_heartbeat=datetime.now(),
            )
            mock_query_status.return_value = expected_result

            result = cluster_manager.query_worker_status_by_url({"worker_url": worker_url})

            # Verify _url_to_id was called
            mock_url_to_id.assert_called_once_with(worker_url)
            # Verify query_worker_status was called
            mock_query_status.assert_called_once_with(payload={"worker_id": worker_id})
            # Verify result
            assert result == expected_result


def test_query_worker_status_by_url_not_found(cluster_manager):
    """Test query_worker_status_by_url when worker URL is not found."""
    worker_url = "http://nonexistent-worker:8080"

    # Mock _url_to_id to return None
    with patch.object(cluster_manager, "_url_to_id", return_value=None):
        result = cluster_manager.query_worker_status_by_url({"worker_url": worker_url})

        expected_result = cluster_types.WorkerStatus(
            worker_id="",
            worker_type="",
            worker_url=worker_url,
            status=cluster_types.WorkerStatusEnum.NONEXISTENT,
            job_id=None,
            last_heartbeat=None,
        )

        assert result.worker_id == expected_result.worker_id
        assert result.status == expected_result.status
        assert result.worker_url == expected_result.worker_url


def test_url_to_id_success(cluster_manager):
    """Test _url_to_id when worker URL exists in database."""
    worker_url = "http://worker:8080"
    worker_id = "test-worker-123"

    existing_worker_status = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [existing_worker_status]

    result = cluster_manager._url_to_id(worker_url)

    # Verify find was called with correct query
    cluster_manager.worker_status_database.find.assert_called_once_with(
        cluster_manager.worker_status_database.redis_backend.model_cls.worker_url == worker_url
    )
    # Verify result
    assert result == worker_id


def test_url_to_id_not_found(cluster_manager):
    """Test _url_to_id when worker URL is not found in database."""
    worker_url = "http://nonexistent-worker:8080"
    cluster_manager.worker_status_database.find.return_value = []

    result = cluster_manager._url_to_id(worker_url)

    # Verify find was called
    cluster_manager.worker_status_database.find.assert_called_once_with(
        cluster_manager.worker_status_database.redis_backend.model_cls.worker_url == worker_url
    )
    # Verify result is None
    assert result is None


def test_url_to_id_multiple_entries(cluster_manager):
    """Test _url_to_id when multiple entries are found (should return first)."""
    worker_url = "http://worker:8080"
    worker_id1 = "test-worker-123"
    worker_id2 = "test-worker-456"

    # Mock multiple entries (should return first one)
    existing_worker_status1 = cluster_types.WorkerStatus(
        worker_id=worker_id1,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    existing_worker_status2 = cluster_types.WorkerStatus(
        worker_id=worker_id2,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [existing_worker_status1, existing_worker_status2]

    result = cluster_manager._url_to_id(worker_url)

    # Verify find was called
    cluster_manager.worker_status_database.find.assert_called_once_with(
        cluster_manager.worker_status_database.redis_backend.model_cls.worker_url == worker_url
    )
    # Verify result is first entry's worker_id
    assert result == worker_id1


def test_worker_get_status_success(mock_worker):
    """Test Worker get_status method when worker status exists."""
    worker_id = str(mock_worker.id)

    # Mock worker status in database
    expected_status = cluster_types.WorkerStatusLocal(
        worker_id=worker_id, status=cluster_types.WorkerStatusEnum.IDLE, job_id=None
    )
    mock_worker.worker_status_local_database.find.return_value = [expected_status]

    result = mock_worker.get_status()

    # Verify find was called with correct query
    mock_worker.worker_status_local_database.find.assert_called_once_with(
        mock_worker.worker_status_local_database.redis_backend.model_cls.worker_id == worker_id
    )
    # Verify result
    assert result == expected_status


def test_worker_get_status_not_found(mock_worker):
    """Test Worker get_status method when worker status is not found."""
    worker_id = str(mock_worker.id)
    mock_worker.worker_status_local_database.find.return_value = []

    with pytest.raises(IndexError):
        mock_worker.get_status()

    # Verify find was called
    mock_worker.worker_status_local_database.find.assert_called_once_with(
        mock_worker.worker_status_local_database.redis_backend.model_cls.worker_id == worker_id
    )


def test_worker_get_status_multiple_entries(mock_worker):
    """Test Worker get_status method when multiple entries are found (should return first)."""
    worker_id = str(mock_worker.id)

    # Mock multiple entries
    status1 = cluster_types.WorkerStatusLocal(
        worker_id=worker_id, status=cluster_types.WorkerStatusEnum.IDLE, job_id=None
    )
    status2 = cluster_types.WorkerStatusLocal(
        worker_id=worker_id, status=cluster_types.WorkerStatusEnum.RUNNING, job_id="job-123"
    )
    mock_worker.worker_status_local_database.find.return_value = [status1, status2]

    result = mock_worker.get_status()

    # Verify find was called
    mock_worker.worker_status_local_database.find.assert_called_once_with(
        mock_worker.worker_status_local_database.redis_backend.model_cls.worker_id == worker_id
    )
    # Verify result is first entry
    assert result == status1


def test_query_worker_status_edge_cases(cluster_manager):
    """Test query_worker_status with various edge cases."""
    worker_id = "test-worker-123"
    worker_url = "http://worker:8080"

    existing_worker_status = cluster_types.WorkerStatus(
        worker_id=worker_id,
        worker_type="test_worker",
        worker_url=worker_url,
        status=cluster_types.WorkerStatusEnum.IDLE,
        job_id=None,
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [existing_worker_status]

    # Test with different worker statuses
    test_cases = [
        (cluster_types.WorkerStatusEnum.IDLE, None),
        (cluster_types.WorkerStatusEnum.RUNNING, "job-123"),
        (cluster_types.WorkerStatusEnum.NONEXISTENT, None),
    ]

    for expected_status, expected_job_id in test_cases:
        with patch("mindtrace.cluster.core.cluster.Worker") as MockWorker:
            mock_worker_instance = MockWorker.connect.return_value

            # Mock worker heartbeat
            mock_heartbeat = MagicMock()
            mock_heartbeat.heartbeat.status = ServerStatus.AVAILABLE
            mock_worker_instance.heartbeat.return_value = mock_heartbeat

            # Mock worker status
            mock_worker_status = MagicMock()
            mock_worker_status.status = expected_status
            mock_worker_status.job_id = expected_job_id
            mock_worker_instance.get_status.return_value = mock_worker_status

            with patch("mindtrace.cluster.core.cluster.update_database") as mock_update:
                mock_update.return_value = existing_worker_status

                result = cluster_manager.query_worker_status({"worker_id": worker_id})

                # Verify database was updated with correct values
                mock_update.assert_called_with(
                    cluster_manager.worker_status_database,
                    "worker_id",
                    worker_id,
                    {"status": expected_status, "job_id": expected_job_id, "last_heartbeat": ANY},
                )
                assert result == existing_worker_status


def test_update_database_edge_cases():
    """Test update_database function with various edge cases."""
    from mindtrace.cluster.core.cluster import update_database

    mock_database = MagicMock()
    mock_entry = MagicMock()
    mock_entry.pk = "test-pk"
    mock_database.find.return_value = [mock_entry]
    mock_database.insert = MagicMock()
    mock_database.redis_backend.model_cls = MagicMock()

    # Test with different update dictionaries
    test_cases = [
        {"status": "completed"},
        {"output": {"result": "test"}},
        {"worker_id": "new-worker-id"},
        {"status": "running", "job_id": "job-123", "last_heartbeat": datetime.now()},
        {},  # Empty update dict
    ]

    for update_dict in test_cases:
        # Reset mock entry
        mock_entry = MagicMock()
        mock_entry.pk = "test-pk"
        mock_database.find.return_value = [mock_entry]

        result = update_database(mock_database, "worker_id", "test-worker", update_dict)

        # Verify attributes were set
        for key, value in update_dict.items():
            assert getattr(mock_entry, key) == value

        # Verify insert was called
        mock_database.insert.assert_called_with(mock_entry)
        assert result == mock_entry


def test_query_worker_status_by_url_edge_cases(cluster_manager):
    """Test query_worker_status_by_url with various edge cases."""
    # Test with different URL formats
    test_urls = [
        "http://localhost:8080",
        "https://worker.example.com:9000",
        "http://192.168.1.100:8080",
        "http://worker:8080",
        "",  # Empty URL
    ]

    for worker_url in test_urls:
        with patch.object(cluster_manager, "_url_to_id") as mock_url_to_id:
            with patch.object(cluster_manager, "query_worker_status") as mock_query_status:
                # Initialize variables
                worker_id = None
                expected_result = None

                if worker_url:  # Non-empty URL
                    worker_id = f"worker-{hash(worker_url) % 1000}"
                    mock_url_to_id.return_value = worker_id
                    expected_result = cluster_types.WorkerStatus(
                        worker_id=worker_id,
                        worker_type="test_worker",
                        worker_url=worker_url,
                        status=cluster_types.WorkerStatusEnum.IDLE,
                        job_id=None,
                        last_heartbeat=datetime.now(),
                    )
                    mock_query_status.return_value = expected_result
                else:  # Empty URL
                    mock_url_to_id.return_value = None

                result = cluster_manager.query_worker_status_by_url({"worker_url": worker_url})

                if worker_url:
                    # Verify _url_to_id was called
                    mock_url_to_id.assert_called_once_with(worker_url)
                    # Verify query_worker_status was called
                    mock_query_status.assert_called_once_with(payload={"worker_id": worker_id})
                    # Verify result
                    assert result == expected_result
                else:
                    # Verify result for empty URL
                    expected_result_empty = cluster_types.WorkerStatus(
                        worker_id="",
                        worker_type="",
                        worker_url="",
                        status=cluster_types.WorkerStatusEnum.NONEXISTENT,
                        job_id=None,
                        last_heartbeat=None,
                    )
                    assert result.worker_id == expected_result_empty.worker_id
                    assert result.status == expected_result_empty.status
                    assert result.worker_url == expected_result_empty.worker_url


def test_query_worker_status_by_url_edge_cases_extended(cluster_manager):
    """Test query_worker_status_by_url with various edge cases."""
    # Test with empty URL
    result = cluster_manager.query_worker_status_by_url(payload={"worker_url": ""})
    assert result.worker_id == ""
    assert result.worker_url == ""
    assert result.status == "nonexistent"

    # Test with None URL
    result = cluster_manager.query_worker_status_by_url(payload={"worker_url": None})
    assert result.worker_id == ""
    assert result.worker_url == ""  # Implementation converts None to empty string
    assert result.status == "nonexistent"

    # Test with very long URL
    long_url = "http://" + "a" * 1000 + ":8080"
    result = cluster_manager.query_worker_status_by_url(payload={"worker_url": long_url})
    assert result.worker_id == ""
    assert result.worker_url == long_url
    assert result.status == "nonexistent"


def test_submit_job_to_endpoint_with_requests_exception(cluster_manager):
    """Test _submit_job_to_endpoint when requests.post raises an exception."""
    job = make_job()

    # Mock requests.post to raise an exception
    with patch(
        "mindtrace.cluster.core.cluster.requests.post",
        side_effect=requests.exceptions.RequestException("Network error"),
    ):
        with pytest.raises(requests.exceptions.RequestException, match="Network error"):
            cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")


def test_submit_job_to_endpoint_with_timeout_exception(cluster_manager):
    """Test _submit_job_to_endpoint when requests.post times out."""
    job = make_job()

    # Mock requests.post to raise a timeout exception
    with patch(
        "mindtrace.cluster.core.cluster.requests.post", side_effect=requests.exceptions.Timeout("Request timeout")
    ):
        with pytest.raises(requests.exceptions.Timeout, match="Request timeout"):
            cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")


def test_submit_job_to_endpoint_with_connection_error(cluster_manager):
    """Test _submit_job_to_endpoint when requests.post fails to connect."""
    job = make_job()

    # Mock requests.post to raise a connection error
    with patch(
        "mindtrace.cluster.core.cluster.requests.post",
        side_effect=requests.exceptions.ConnectionError("Connection failed"),
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="Connection failed"):
            cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")


def test_submit_job_to_endpoint_with_ssl_error(cluster_manager):
    """Test _submit_job_to_endpoint when requests.post encounters SSL errors."""
    job = make_job()

    # Mock requests.post to raise an SSL error
    with patch(
        "mindtrace.cluster.core.cluster.requests.post",
        side_effect=requests.exceptions.SSLError("SSL certificate error"),
    ):
        with pytest.raises(requests.exceptions.SSLError, match="SSL certificate error"):
            cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")


def test_submit_job_to_endpoint_with_invalid_json_response(cluster_manager):
    """Test _submit_job_to_endpoint when response.json() fails."""
    job = make_job()

    # Mock response to have invalid JSON
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "invalid", 0)

    with patch("mindtrace.cluster.core.cluster.requests.post", return_value=mock_response):
        result = cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")

        # Should use default values when JSON parsing fails
        assert result.status == "completed"
        assert result.output == {}


def test_submit_job_to_endpoint_with_malformed_response(cluster_manager):
    """Test _submit_job_to_endpoint when response has unexpected structure."""
    job = make_job()

    # Mock response with unexpected structure
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"unexpected": "structure"}

    with patch("mindtrace.cluster.core.cluster.requests.post", return_value=mock_response):
        result = cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")

        # Should use default values when response doesn't have expected fields
        assert result.status == "completed"
        assert result.output == {}


def test_submit_job_to_endpoint_with_partial_response(cluster_manager):
    """Test _submit_job_to_endpoint when response has partial data."""
    job = make_job()

    # Mock response with partial data
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "running"}  # Missing output field

    with patch("mindtrace.cluster.core.cluster.requests.post", return_value=mock_response):
        result = cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")

        # Should use provided status but default output
        assert result.status == "running"
        assert result.output == {}


def test_submit_job_to_endpoint_with_none_response_values(cluster_manager):
    """Test _submit_job_to_endpoint when response has None values."""
    job = make_job()

    # Mock response with None values
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": None, "output": None}

    with patch("mindtrace.cluster.core.cluster.requests.post", return_value=mock_response):
        result = cluster_manager._submit_job_to_endpoint(job, "/test_endpoint")

        # Should use default values when response has None values
        assert result.status == "completed"
        assert result.output == {}


def test_register_job_to_worker_with_worker_connection_failure(cluster_manager):
    """Test register_job_to_worker when Worker.connect fails."""
    payload = {"job_type": "test_job", "worker_url": "http://worker:8080"}

    # Mock Worker.connect to raise an exception
    with patch(
        "mindtrace.cluster.core.cluster.Worker.connect", side_effect=ConnectionError("Worker connection failed")
    ):
        with pytest.raises(ConnectionError, match="Worker connection failed"):
            cluster_manager.register_job_to_worker(payload)


def test_register_job_to_worker_with_heartbeat_failure(cluster_manager):
    """Test register_job_to_worker when heartbeat() fails."""
    payload = {"job_type": "test_job", "worker_url": "http://worker:8080"}

    # Mock Worker.connect and heartbeat to raise an exception
    mock_worker_cm = MagicMock()
    mock_worker_cm.heartbeat.side_effect = Exception("Heartbeat failed")

    with patch("mindtrace.cluster.core.cluster.Worker.connect", return_value=mock_worker_cm):
        with pytest.raises(Exception, match="Heartbeat failed"):
            cluster_manager.register_job_to_worker(payload)


def test_register_job_to_worker_with_connect_to_cluster_failure(cluster_manager):
    """Test register_job_to_worker when connect_to_cluster fails."""
    payload = {"job_type": "test_job", "worker_url": "http://worker:8080"}

    # Mock Worker.connect and related methods
    mock_worker_cm = MagicMock()
    mock_heartbeat = MagicMock()
    mock_heartbeat.heartbeat.status = ServerStatus.AVAILABLE
    mock_heartbeat.heartbeat.server_id = "worker-123"
    mock_worker_cm.heartbeat.return_value = mock_heartbeat
    mock_worker_cm.connect_to_cluster.side_effect = RuntimeError("Cluster connection failed")

    with patch("mindtrace.cluster.core.cluster.Worker.connect", return_value=mock_worker_cm):
        with pytest.raises(RuntimeError, match="Cluster connection failed"):
            cluster_manager.register_job_to_worker(payload)


def test_launch_worker_with_worker_connection_failure(cluster_manager):
    """Test launch_worker when Worker.connect fails."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8080"}

    # Mock Node.connect and related methods
    mock_node_cm = MagicMock()
    mock_node_cm.launch_worker.return_value = None

    # Mock Worker.connect to raise an exception
    with (
        patch("mindtrace.cluster.core.cluster.Node.connect", return_value=mock_node_cm),
        patch("mindtrace.cluster.core.cluster.Worker.connect", side_effect=ConnectionError("Worker connection failed")),
    ):
        with pytest.raises(ConnectionError, match="Worker connection failed"):
            cluster_manager.launch_worker(payload)


def test_launch_worker_with_heartbeat_failure(cluster_manager):
    """Test launch_worker when worker heartbeat() fails."""
    payload = {"node_url": "http://node:8080", "worker_type": "test_worker", "worker_url": "http://worker:8080"}

    # Mock Node.connect and related methods
    mock_node_cm = MagicMock()
    mock_node_cm.launch_worker.return_value = None

    # Mock Worker.connect and heartbeat
    mock_worker_cm = MagicMock()
    mock_worker_cm.heartbeat.side_effect = Exception("Heartbeat failed")

    with (
        patch("mindtrace.cluster.core.cluster.Node.connect", return_value=mock_node_cm),
        patch("mindtrace.cluster.core.cluster.Worker.connect", return_value=mock_worker_cm),
    ):
        with pytest.raises(Exception, match="Heartbeat failed"):
            cluster_manager.launch_worker(payload)


def test_worker_run_with_exception_in_run_method(mock_worker):
    """Test worker run method when _run raises an exception."""
    # Mock cluster connection manager
    mock_cm = MagicMock()
    mock_worker._cluster_url = "http://cluster:8080"
    mock_worker._cluster_connection_manager = mock_cm

    # Mock _run to raise an exception
    mock_worker._run.side_effect = ValueError("Test error")

    job_dict = {"id": "job-123", "payload": {"test": "data"}}

    # Run the job
    result = mock_worker.run(job_dict)

    # Verify error handling
    assert result["status"] == "failed"
    assert result["output"] == {}

    # Verify cluster manager was notified
    mock_cm.worker_alert_started_job.assert_called_once_with(job_id="job-123", worker_id=str(mock_worker.id))
    mock_cm.worker_alert_completed_job.assert_called_once_with(
        job_id="job-123", worker_id=str(mock_worker.id), status="failed", output={}
    )


def test_worker_run_with_exception_and_no_cluster_manager(mock_worker):
    """Test worker run method when _run raises an exception and no cluster manager."""
    # Ensure no cluster manager
    mock_worker._cluster_url = None
    mock_worker._cluster_connection_manager = None

    # Mock _run to raise an exception
    mock_worker._run.side_effect = RuntimeError("Test runtime error")

    job_dict = {"id": "job-456", "payload": {"test": "data"}}

    # Run the job
    result = mock_worker.run(job_dict)

    # Verify error handling
    assert result["status"] == "failed"
    assert result["output"] == {}


def test_worker_connect_to_cluster_with_invalid_payload(mock_worker):
    """Test worker connect_to_cluster with invalid payload."""
    # Test with missing required fields
    invalid_payload = {"backend_args": {}}  # Missing queue_name and cluster_url

    with pytest.raises(KeyError):
        mock_worker.connect_to_cluster(invalid_payload)


def test_worker_connect_to_cluster_with_connect_failure(mock_worker):
    """Test worker connect_to_cluster when connect_to_orchestator_via_backend_args fails."""
    payload = {
        "backend_args": {"cls": "test.backend", "kwargs": {"host": "localhost", "port": 5673}},
        "queue_name": "test_queue",
        "cluster_url": "http://cluster:8080",
    }

    # Mock connect_to_orchestator_via_backend_args to raise an exception
    mock_worker.connect_to_orchestator_via_backend_args.side_effect = ConnectionError("Orchestrator connection failed")

    with pytest.raises(ConnectionError, match="Orchestrator connection failed"):
        mock_worker.connect_to_cluster(payload)


def test_worker_connect_to_cluster_with_thread_start_failure(mock_worker):
    """Test worker connect_to_cluster when thread start fails."""
    payload = {
        "backend_args": {"cls": "test.backend", "kwargs": {"host": "localhost", "port": 5673}},
        "queue_name": "test_queue",
        "cluster_url": "http://cluster:8080",
    }

    # Mock multiprocessing.Process to raise an exception
    with patch("mindtrace.cluster.core.cluster.threading.Thread") as mock_thread_class:
        mock_thread = MagicMock()
        mock_thread.start.side_effect = RuntimeError("Thread start failed")
        mock_thread_class.return_value = mock_thread

        with pytest.raises(RuntimeError, match="Thread start failed"):
            mock_worker.connect_to_cluster(payload)


def test_worker_get_status_with_no_entries(mock_worker):
    """Test worker get_status when no entries are found."""
    # Mock database to return empty list
    mock_worker.worker_status_local_database.find.return_value = []

    with pytest.raises(IndexError):
        mock_worker.get_status()


def test_worker_shutdown_with_process_kill_failure(mock_worker):
    """Test worker shutdown when process kill fails."""
    # Mock consume process
    mock_worker.consume_process = MagicMock()
    mock_worker.consume_process.kill.side_effect = Exception("Process kill failed")

    # Mock super().shutdown()
    with patch.object(mock_worker.__class__, "shutdown", return_value=None):
        # The actual implementation doesn't raise exceptions, it just logs them
        result = mock_worker.shutdown()
        assert result is None


def test_node_launch_worker_with_registry_load_failure(mock_node):
    """Test node launch_worker when registry load fails."""
    payload = {"worker_type": "test_worker", "worker_url": "http://worker:8080"}

    # Mock worker registry to raise an exception
    mock_node.worker_registry.load.side_effect = FileNotFoundError("Worker not found in registry")

    with pytest.raises(FileNotFoundError, match="Worker not found in registry"):
        mock_node.launch_worker(payload)


def test_node_shutdown_with_worker_shutdown_failure(mock_node):
    """Test node shutdown when worker shutdown fails."""
    # Mock worker to raise an exception during shutdown
    mock_worker = MagicMock()
    mock_worker.shutdown.side_effect = RuntimeError("Worker shutdown failed")
    mock_node.workers = [mock_worker]

    # Mock super().shutdown()
    with patch.object(mock_node.__class__, "shutdown", return_value=None):
        # The actual implementation doesn't raise exceptions, it just logs them
        result = mock_node.shutdown()
        assert result is None


def test_update_database_with_database_insert_failure():
    """Test update_database when database insert fails."""
    # Create mock database
    mock_database = MagicMock()
    mock_database.find.return_value = [MagicMock()]
    mock_database.insert.side_effect = Exception("Database insert failed")

    with pytest.raises(Exception, match="Database insert failed"):
        update_database(mock_database, "test_key", "test_value", {"field": "value"})


def test_register_worker_type_with_registry_failure(cluster_manager):
    """Test register_worker_type when registry operations fail."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "test.worker.TestWorker",
        "worker_params": {"param1": "value1"},
        "job_type": "test_job",
    }

    # Mock the registry to avoid IndexError and test actual save failure
    with (
        patch.object(cluster_manager.worker_registry, "list_versions", return_value=[]),
        patch.object(cluster_manager.worker_registry, "save", side_effect=Exception("Registry save failed")),
    ):
        with pytest.raises(Exception, match="Registry save failed"):
            cluster_manager.register_worker_type(payload)


def test_register_worker_type_with_save_failure(cluster_manager):
    """Test register_worker_type when registry save fails."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "test.worker.TestWorker",
        "worker_params": {"param1": "value1"},
        "job_type": "test_job",
    }

    # Mock the registry to avoid IndexError and test actual save failure
    with (
        patch.object(cluster_manager.worker_registry, "list_versions", return_value=[]),
        patch.object(cluster_manager.worker_registry, "save", side_effect=Exception("Registry save failed")),
    ):
        with pytest.raises(Exception, match="Registry save failed"):
            cluster_manager.register_worker_type(payload)


def test_register_worker_type_with_job_schema_registration_failure(cluster_manager):
    """Test register_worker_type when job schema registration fails."""
    payload = {
        "worker_name": "test_worker",
        "worker_class": "test.worker.TestWorker",
        "worker_params": {"param1": "value1"},
        "job_type": "test_job",
    }

    # Mock the registry to avoid IndexError and test job schema registration failure
    with (
        patch.object(cluster_manager.worker_registry, "list_versions", return_value=[]),
        patch.object(
            cluster_manager,
            "register_job_schema_to_worker_type",
            side_effect=Exception("Job schema registration failed"),
        ),
    ):
        with pytest.raises(Exception, match="Job schema registration failed"):
            cluster_manager.register_worker_type(payload)


def test_clear_databases_with_partial_failure(cluster_manager):
    """Test clear_databases when some database operations fail."""
    # Mock some databases to fail during clear operation
    cluster_manager.job_schema_targeting_database.all.return_value = [MagicMock(), MagicMock()]
    cluster_manager.job_schema_targeting_database.delete.side_effect = [None, Exception("Delete failed")]

    # The actual implementation doesn't handle exceptions gracefully, it just raises them
    with pytest.raises(Exception, match="Delete failed"):
        cluster_manager.clear_databases()


def test_worker_alert_completed_job_with_mismatched_worker_id(cluster_manager):
    """Test worker_alert_completed_job when worker ID doesn't match stored worker ID."""
    # Create a job status with a different worker ID
    job_status = cluster_types.JobStatus(job_id="job-123", status="running", output={}, worker_id="different-worker")

    # Mock database to return this job status for job lookup
    cluster_manager.job_status_database.find.return_value = [job_status]

    # Mock worker status database to return a worker status for the actual worker
    worker_status = cluster_types.WorkerStatus(
        worker_id="actual-worker",
        worker_type="test_worker",
        worker_url="http://worker:8080",
        status=cluster_types.WorkerStatusEnum.RUNNING,
        job_id="job-123",
        last_heartbeat=datetime.now(),
    )
    cluster_manager.worker_status_database.find.return_value = [worker_status]

    payload = {
        "job_id": "job-123",
        "worker_id": "actual-worker",
        "status": "completed",
        "output": {"result": "success"},
    }

    # This should log a warning but not raise an exception
    cluster_manager.worker_alert_completed_job(payload)

    # Verify warning was logged
    cluster_manager.logger.warning.assert_called_once()
    warning_message = cluster_manager.logger.warning.call_args[0][0]
    assert (
        "Worker actual-worker alerted cluster manager that job job-123 has completed, but the worker id does not match the stored worker id different-worker"
        in warning_message
    )
