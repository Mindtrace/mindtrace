import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.jobs.core.orchestrator import Orchestrator
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.types.job_specs import ExecutionStatus, Job, JobSchema


class MockInputSchema(BaseModel):
    """Mock input schema for testing."""

    data: str


class MockOutputSchema(BaseModel):
    """Mock output schema for testing."""

    result: str


class MockTaskSchema(TaskSchema):
    """Mock task schema for testing."""

    name: str = "test-schema"
    schema_name: str = "test-schema"  # Add schema_name field for orchestrator compatibility
    input_schema: type[BaseModel] = MockInputSchema
    output_schema: type[BaseModel] = MockOutputSchema


class MockJobSchema(JobSchema):
    """Mock job schema for testing."""

    name: str = "test-schema"
    input_schema: type[BaseModel] = MockInputSchema
    output_schema: type[BaseModel] = MockOutputSchema


@pytest.fixture
def mock_backend():
    """Provide a mock backend for testing."""
    backend = MagicMock()
    backend.publish.return_value = "test-job-id"
    backend.clean_queue.return_value = {"status": "success"}
    backend.delete_queue.return_value = {"status": "success"}
    backend.count_queue_messages.return_value = 5
    backend.declare_queue.return_value = {"status": "success"}
    return backend


@pytest.fixture
def orchestrator(mock_backend):
    """Provide an orchestrator instance with mock backend."""
    return Orchestrator(backend=mock_backend)


@pytest.fixture
def sample_job():
    """Provide a sample Job instance."""
    return Job(
        id=str(uuid4()),
        name="test-job",
        schema_name="test-schema",
        payload={"data": "test"},
        status=ExecutionStatus.QUEUED,
        created_at=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_task_schema():
    """Provide a sample TaskSchema instance."""
    return MockTaskSchema(name="test-schema", schema_name="test-schema", data="test-data")


class TestOrchestratorInitialization:
    """Tests for Orchestrator initialization."""

    def test_init_with_backend(self, mock_backend):
        """Test initialization with custom backend."""
        orchestrator = Orchestrator(backend=mock_backend)
        assert orchestrator.backend is mock_backend
        assert orchestrator._schema_mapping == {}

    def test_init_without_backend(self):
        """Test initialization without backend (uses default)."""
        orchestrator = Orchestrator()
        assert isinstance(orchestrator.backend, LocalClient)
        assert orchestrator._schema_mapping == {}

    def test_init_with_none_backend(self):
        """Test initialization with None backend (uses default)."""
        orchestrator = Orchestrator(backend=None)
        assert isinstance(orchestrator.backend, LocalClient)
        assert orchestrator._schema_mapping == {}

    def test_init_with_orchestrator_dir(self):
        """Test initialization with orchestrator_dir parameter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(orchestrator_dir=temp_dir)
            assert isinstance(orchestrator.backend, LocalClient)
            assert orchestrator._schema_mapping == {}


class TestOrchestratorPublish:
    """Tests for Orchestrator publish method."""

    def test_publish_job_object(self, orchestrator, sample_job, mock_backend):
        """Test publishing a Job object directly."""
        result = orchestrator.publish("test-queue", sample_job)

        assert result == "test-job-id"
        mock_backend.publish.assert_called_once_with("test-queue", sample_job)

    def test_publish_job_object_with_kwargs(self, orchestrator, sample_job, mock_backend):
        """Test publishing a Job object with additional kwargs."""
        result = orchestrator.publish("test-queue", sample_job, priority=10)

        assert result == "test-job-id"
        mock_backend.publish.assert_called_once_with("test-queue", sample_job, priority=10)

    def test_publish_task_schema_registered(self, orchestrator, sample_task_schema, mock_backend):
        """Test publishing a TaskSchema that is registered."""
        # Register the schema first
        schema = MockJobSchema()
        orchestrator.register(schema)

        with patch("mindtrace.jobs.core.orchestrator.job_from_schema") as mock_job_from_schema:
            mock_job = MagicMock()
            mock_job_from_schema.return_value = mock_job

            result = orchestrator.publish("test-schema", sample_task_schema)

            assert result == "test-job-id"
            # Get the actual schema from orchestrator's mapping
            actual_schema = orchestrator._schema_mapping[sample_task_schema.schema_name]["schema"]
            mock_job_from_schema.assert_called_once_with(actual_schema, sample_task_schema)
            mock_backend.publish.assert_called_once_with("test-schema", mock_job)

    def test_publish_task_schema_not_registered(self, orchestrator, sample_task_schema):
        """Test publishing a TaskSchema that is not registered."""
        with pytest.raises(ValueError, match="Schema 'test-schema' not found."):
            orchestrator.publish("test-schema", sample_task_schema)

    def test_publish_invalid_job_type(self, orchestrator):
        """Test publishing an invalid job type."""
        invalid_job = {"invalid": "job"}

        with pytest.raises(ValueError, match="Invalid job type: <class 'dict'>, expected Job or TaskSchema."):
            orchestrator.publish("test-queue", invalid_job)

    def test_publish_backend_error(self, orchestrator, sample_job, mock_backend):
        """Test publishing when backend raises an error."""
        mock_backend.publish.side_effect = Exception("Backend error")

        with pytest.raises(Exception, match="Backend error"):
            orchestrator.publish("test-queue", sample_job)


class TestOrchestratorQueueManagement:
    """Tests for Orchestrator queue management methods."""

    def test_clean_queue(self, orchestrator, mock_backend):
        """Test cleaning a queue."""
        orchestrator.clean_queue("test-queue")
        mock_backend.clean_queue.assert_called_once_with("test-queue")

    def test_clean_queue_with_kwargs(self, orchestrator, mock_backend):
        """Test cleaning a queue with additional kwargs."""
        orchestrator.clean_queue("test-queue", force=True)
        mock_backend.clean_queue.assert_called_once_with("test-queue", force=True)

    def test_delete_queue(self, orchestrator, mock_backend):
        """Test deleting a queue."""
        orchestrator.delete_queue("test-queue")
        mock_backend.delete_queue.assert_called_once_with("test-queue")

    def test_delete_queue_with_kwargs(self, orchestrator, mock_backend):
        """Test deleting a queue with additional kwargs."""
        orchestrator.delete_queue("test-queue", force=True)
        mock_backend.delete_queue.assert_called_once_with("test-queue", force=True)

    def test_count_queue_messages(self, orchestrator, mock_backend):
        """Test counting queue messages."""
        result = orchestrator.count_queue_messages("test-queue")

        assert result == 5
        mock_backend.count_queue_messages.assert_called_once_with("test-queue")

    def test_count_queue_messages_with_kwargs(self, orchestrator, mock_backend):
        """Test counting queue messages with additional kwargs."""
        result = orchestrator.count_queue_messages("test-queue", include_dlq=True)

        assert result == 5
        mock_backend.count_queue_messages.assert_called_once_with("test-queue", include_dlq=True)

    def test_queue_management_backend_errors(self, orchestrator, mock_backend):
        """Test queue management when backend raises errors."""
        # Test clean_queue error
        mock_backend.clean_queue.side_effect = Exception("Clean error")
        with pytest.raises(Exception, match="Clean error"):
            orchestrator.clean_queue("test-queue")

        # Test delete_queue error
        mock_backend.delete_queue.side_effect = Exception("Delete error")
        with pytest.raises(Exception, match="Delete error"):
            orchestrator.delete_queue("test-queue")

        # Test count_queue_messages error
        mock_backend.count_queue_messages.side_effect = Exception("Count error")
        with pytest.raises(Exception, match="Count error"):
            orchestrator.count_queue_messages("test-queue")


class TestOrchestratorRegister:
    """Tests for Orchestrator register method."""

    def test_register_schema(self, orchestrator, mock_backend):
        """Test registering a schema."""
        schema = MockJobSchema()

        result = orchestrator.register(schema)

        assert result == "test-schema"
        mock_backend.declare_queue.assert_called_once_with("test-schema", queue_type="fifo")
        assert "test-schema" in orchestrator._schema_mapping
        assert orchestrator._schema_mapping["test-schema"]["schema"] == schema
        assert orchestrator._schema_mapping["test-schema"]["queue_name"] == "test-schema"

    def test_register_schema_custom_queue_type(self, orchestrator, mock_backend):
        """Test registering a schema with custom queue type."""
        schema = MockJobSchema()

        result = orchestrator.register(schema, queue_type="priority")

        assert result == "test-schema"
        mock_backend.declare_queue.assert_called_once_with("test-schema", queue_type="priority")

    def test_register_schema_backend_error(self, orchestrator, mock_backend):
        """Test registering a schema when backend raises an error."""
        schema = MockJobSchema()
        mock_backend.declare_queue.side_effect = Exception("Declare error")

        with pytest.raises(Exception, match="Declare error"):
            orchestrator.register(schema)

    def test_register_multiple_schemas(self, orchestrator, mock_backend):
        """Test registering multiple schemas."""
        schema1 = MockJobSchema()
        schema1.name = "schema1"
        schema2 = MockJobSchema()
        schema2.name = "schema2"

        result1 = orchestrator.register(schema1)
        result2 = orchestrator.register(schema2)

        assert result1 == "schema1"
        assert result2 == "schema2"
        assert len(orchestrator._schema_mapping) == 2
        assert "schema1" in orchestrator._schema_mapping
        assert "schema2" in orchestrator._schema_mapping


class TestOrchestratorIntegration:
    """Integration tests for Orchestrator functionality."""

    def test_publish_after_register(self, orchestrator, sample_task_schema, mock_backend):
        """Test publishing a TaskSchema after registering its schema."""
        # Register the schema
        schema = MockJobSchema()
        orchestrator.register(schema)

        # Publish using TaskSchema
        with patch("mindtrace.jobs.core.orchestrator.job_from_schema") as mock_job_from_schema:
            mock_job = MagicMock()
            mock_job_from_schema.return_value = mock_job

            result = orchestrator.publish("test-schema", sample_task_schema)

            assert result == "test-job-id"
            # Get the actual schema from orchestrator's mapping
            actual_schema = orchestrator._schema_mapping[sample_task_schema.schema_name]["schema"]
            mock_job_from_schema.assert_called_once_with(actual_schema, sample_task_schema)

    def test_schema_mapping_persistence(self, orchestrator):
        """Test that schema mapping persists across operations."""
        schema = MockJobSchema()

        # Register schema
        orchestrator.register(schema)
        assert "test-schema" in orchestrator._schema_mapping

        # Verify mapping is still there
        assert orchestrator._schema_mapping["test-schema"]["schema"] == schema

    def test_multiple_operations_same_queue(self, orchestrator, sample_job, mock_backend):
        """Test multiple operations on the same queue."""
        queue_name = "test-queue"

        # Publish job
        orchestrator.publish(queue_name, sample_job)

        # Count messages
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 5

        # Clean queue
        orchestrator.clean_queue(queue_name)

        # Delete queue
        orchestrator.delete_queue(queue_name)

        # Verify all backend calls
        assert mock_backend.publish.call_count == 1
        assert mock_backend.count_queue_messages.call_count == 1
        assert mock_backend.clean_queue.call_count == 1
        assert mock_backend.delete_queue.call_count == 1


class TestOrchestratorEdgeCases:
    """Tests for Orchestrator edge cases and error conditions."""

    def test_publish_with_empty_queue_name(self, orchestrator, sample_job):
        """Test publishing with empty queue name."""
        # The orchestrator doesn't validate empty queue names, so this should pass
        result = orchestrator.publish("", sample_job)
        assert result == "test-job-id"

    def test_register_schema_with_empty_name(self, orchestrator):
        """Test registering a schema with empty name."""
        schema = MockJobSchema()
        schema.name = ""

        # The orchestrator doesn't validate empty schema names, so this should pass
        result = orchestrator.register(schema)
        assert result == ""

    def test_publish_task_schema_with_different_schema_name(self, orchestrator):
        """Test publishing a TaskSchema with a different schema name than registered."""
        # Register schema with name "schema1"
        schema = MockJobSchema()
        schema.name = "schema1"
        orchestrator.register(schema)

        # Try to publish TaskSchema with name "schema2"
        task_schema = MockTaskSchema(name="schema2", schema_name="schema2")

        with pytest.raises(ValueError, match="Schema 'schema2' not found."):
            orchestrator.publish("schema2", task_schema)

    def test_backend_methods_return_values(self, orchestrator, mock_backend):
        """Test that backend method return values are properly handled."""
        # Test different return values
        mock_backend.count_queue_messages.return_value = 0
        assert orchestrator.count_queue_messages("empty-queue") == 0

        mock_backend.count_queue_messages.return_value = 100
        assert orchestrator.count_queue_messages("full-queue") == 100

    def test_schema_mapping_isolation(self, orchestrator):
        """Test that schema mappings are isolated between orchestrator instances."""
        orchestrator1 = Orchestrator()
        orchestrator2 = Orchestrator()

        schema = MockJobSchema()

        # Register schema in orchestrator1
        orchestrator1.register(schema)
        assert "test-schema" in orchestrator1._schema_mapping
        assert "test-schema" not in orchestrator2._schema_mapping
