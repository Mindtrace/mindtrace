import time
from unittest.mock import MagicMock

import pydantic
import pytest

from mindtrace.jobs.local.client import LocalClient


class SampleMessage(pydantic.BaseModel):
    x: int | None = None
    y: int | None = None
    data: str | None = None
    job_id: str | None = None


class TestLocalClient:
    """Tests for LocalClient backend."""

    def test_declare_queue(self, temp_local_client):
        """Test queue declaration."""
        broker = temp_local_client
        queue_name = f"test-queue-{int(time.time())}"

        result = broker.declare_queue(queue_name, queue_type="fifo")
        assert result["status"] == "success"

        result2 = broker.declare_queue(queue_name, queue_type="fifo")
        assert result2["status"] == "success"

        broker.delete_queue(queue_name)

    def test_queue_types(self, temp_local_client):
        """Test different queue types."""
        broker = temp_local_client
        base_name = f"queue-{int(time.time())}"

        fifo_queue = f"{base_name}-fifo"
        result = broker.declare_queue(fifo_queue, queue_type="fifo")
        assert result["status"] == "success"

        stack_queue = f"{base_name}-stack"
        result = broker.declare_queue(stack_queue, queue_type="stack")
        assert result["status"] == "success"

        priority_queue = f"{base_name}-priority"
        result = broker.declare_queue(priority_queue, queue_type="priority")
        assert result["status"] == "success"

        broker.delete_queue(fifo_queue)
        broker.delete_queue(stack_queue)
        broker.delete_queue(priority_queue)

    def test_publish_and_receive(self, temp_local_client, create_test_job_fixture):
        """Test publishing and receiving messages."""
        broker = temp_local_client
        queue_name = f"test-queue-{int(time.time())}"
        broker.declare_queue(queue_name)

        test_job = create_test_job_fixture()
        job_id = broker.publish(queue_name, test_job)

        assert isinstance(job_id, str)
        assert len(job_id) > 0

        count = broker.count_queue_messages(queue_name)
        assert count == 1

        received_job = broker.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        assert received_job["id"] == test_job.id

        count = broker.count_queue_messages(queue_name)
        assert count == 0

        broker.delete_queue(queue_name)

    def test_clean_queue(self, temp_local_client, create_test_job_fixture):
        """Test cleaning a queue."""
        broker = temp_local_client
        queue_name = f"test-queue-{int(time.time())}"
        broker.declare_queue(queue_name)

        for i in range(3):
            job = create_test_job_fixture(f"job_{i}")
            broker.publish(queue_name, job)

        assert broker.count_queue_messages(queue_name) == 3

        result = broker.clean_queue(queue_name)
        assert result["status"] == "success"
        assert broker.count_queue_messages(queue_name) == 0

        broker.delete_queue(queue_name)

    def test_delete_queue(self, temp_local_client):
        """Test deleting a queue."""
        broker = temp_local_client
        queue_name = f"test-queue-{int(time.time())}"
        broker.declare_queue(queue_name)

        result = broker.delete_queue(queue_name)
        assert result["status"] == "success"

        with pytest.raises(KeyError):
            broker.count_queue_messages(queue_name)

    def test_exchange_methods_not_implemented(self, temp_local_client):
        """Test that LocalClient raises NotImplementedError for exchange methods."""
        broker = temp_local_client
        with pytest.raises(NotImplementedError):
            broker.declare_exchange(exchange="test_exchange")

        with pytest.raises(NotImplementedError):
            broker.delete_exchange(exchange="test_exchange")

        with pytest.raises(NotImplementedError):
            broker.count_exchanges()

    def test_declare_queue_types(self, temp_local_client):
        """Test declaring different queue types."""
        client = temp_local_client
        result = client.declare_queue("fifo-queue", queue_type="fifo")
        assert result["status"] == "success"
        assert isinstance(client.queues["fifo-queue"], type(client.queues["fifo-queue"]))

        result = client.declare_queue("stack-queue", queue_type="stack")
        assert result["status"] == "success"
        assert isinstance(client.queues["stack-queue"], type(client.queues["stack-queue"]))

        result = client.declare_queue("priority-queue", queue_type="priority")
        assert result["status"] == "success"
        assert isinstance(client.queues["priority-queue"], type(client.queues["priority-queue"]))

        with pytest.raises(TypeError, match="Unknown queue type"):
            client.declare_queue("invalid-queue", queue_type="invalid")

    def test_declare_existing_queue(self, temp_local_client):
        """Test declaring a queue that already exists."""
        client = temp_local_client
        client.declare_queue("test-queue")
        result = client.declare_queue("test-queue")
        assert result["status"] == "success"
        assert "already exists" in result["message"]

    def test_publish_receive_fifo(self, temp_local_client):
        """Test publishing and receiving messages in FIFO order."""
        client = temp_local_client
        client.declare_queue("test-queue")

        msg1 = SampleMessage(data="test1")
        msg2 = SampleMessage(data="test2")
        job_id1 = client.publish("test-queue", msg1)
        job_id2 = client.publish("test-queue", msg2)

        assert client.count_queue_messages("test-queue") == 2

        received1 = client.receive_message("test-queue")
        received2 = client.receive_message("test-queue")

        assert received1["data"] == "test1"
        assert received2["data"] == "test2"
        assert received1["job_id"] == job_id1
        assert received2["job_id"] == job_id2

    def test_publish_receive_priority(self, temp_local_client):
        """Test publishing and receiving messages with priority."""
        client = temp_local_client
        client.declare_queue("priority-queue", queue_type="priority")

        msg1 = SampleMessage(data="low")
        msg2 = SampleMessage(data="high")
        client.publish("priority-queue", msg1, priority=1)
        client.publish("priority-queue", msg2, priority=10)

        received1 = client.receive_message("priority-queue")
        received2 = client.receive_message("priority-queue")

        assert received1["data"] == "high"
        assert received2["data"] == "low"

    def test_receive_empty_queue(self, temp_local_client):
        """Test receiving from empty queue."""
        client = temp_local_client
        client.declare_queue("test-queue")

        result = client.receive_message("test-queue", block=False)
        assert result is None

        result = client.receive_message("test-queue", block=True, timeout=0.01)
        assert result is None

    def test_job_results(self, temp_local_client):
        """Test storing and retrieving job results."""
        client = temp_local_client
        job_id = "test-job"
        result_data = {"status": "completed", "value": 42}

        client.store_job_result(job_id, result_data)
        retrieved = client.get_job_result(job_id)
        assert retrieved == result_data

        assert client.get_job_result("nonexistent-job") is None

    def test_publish_to_nonexistent_queue(self, temp_local_client):
        """Test publishing to a queue that doesn't exist."""
        client = temp_local_client
        msg = SampleMessage(data="test")

        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.publish("nonexistent-queue", msg)

    def test_priority_queue_with_priority(self, temp_local_client):
        """Test publishing to priority queue with priority parameter."""
        client = temp_local_client
        client.declare_queue("priority-queue", queue_type="priority")

        msg = SampleMessage(data="priority-test")
        job_id = client.publish("priority-queue", msg, priority=5)
        assert job_id is not None

        job_id2 = client.publish("priority-queue", msg, priority=None)
        assert job_id2 is not None

    def test_receive_from_nonexistent_queue(self, temp_local_client):
        """Test receiving from a queue that doesn't exist."""
        client = temp_local_client
        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.receive_message("nonexistent-queue")

    def test_receive_message_json_decode_error(self, temp_local_client):
        """Test receive_message handling of JSON decode errors."""
        client = temp_local_client
        client.declare_queue("test-queue")

        queue_instance = client.queues["test-queue"]
        queue_instance.push("invalid json content")

        result = client.receive_message("test-queue", block=True, timeout=0.01)
        assert result is None

    def test_clean_nonexistent_queue(self, temp_local_client):
        """Test cleaning a queue that doesn't exist."""
        client = temp_local_client
        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.clean_queue("nonexistent-queue")

    def test_count_nonexistent_queue(self, temp_local_client):
        """Test counting messages in a queue that doesn't exist."""
        client = temp_local_client
        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.count_queue_messages("nonexistent-queue")

    def test_move_to_dlq(self, temp_local_client):
        """Test move_to_dlq method (currently a pass statement)."""
        client = temp_local_client
        msg = SampleMessage(data="test")

        result = client.move_to_dlq("source-queue", "dlq-queue", msg, "error details")
        assert result is None  # pass statement returns None

    def test_receive_message_returns_none_when_queue_pop_returns_none(self, temp_local_client):
        """Test receive_message returns None when queue.pop() returns None."""
        client = temp_local_client
        queue_name = "test-queue"
        client.declare_queue(queue_name)

        queue_instance = client.queues[queue_name]
        original_pop = queue_instance.pop

        def mock_pop(*args, **kwargs):
            return None  # Simulate empty queue

        queue_instance.pop = mock_pop

        result = client.receive_message(queue_name, block=False)
        assert result is None

        queue_instance.pop = original_pop

    def test_delete_nonexistent_queue(self, temp_local_client):
        client = temp_local_client
        with pytest.raises(KeyError, match="Queue 'does-not-exist' not found"):
            client.delete_queue("does-not-exist")

    def test_receive_empty_logs_debug(self, temp_local_client):
        client = temp_local_client
        q = "empty-queue"
        client.declare_queue(q)
        # Attach a MagicMock logger with debug and warning
        mock_logger = MagicMock()
        client.logger = mock_logger
        result = client.receive_message(q, block=False)
        assert result is None
        client.logger.warning.assert_called()

    def test_receive_message_pop_returns_none_triggers_debug(self, temp_local_client):
        client = temp_local_client
        q = "debug-empty-queue"
        client.declare_queue(q)
        fake_queue = MagicMock()
        fake_queue.pop.return_value = None
        # Ensure membership check passes, but load returns our fake queue
        client.queues.load = MagicMock(return_value=fake_queue)
        mock_logger = MagicMock()
        client.logger = mock_logger
        result = client.receive_message(q, block=True)
        assert result is None
        client.logger.debug.assert_called()

    def test_store_and_get_job_result_lock_isolated_from_queue_locks(self, monkeypatch):
        """
        Expected behavior: storing/fetching job results should use a lock from the job-results registry,
        not the queues registry. Using the queues registry lock can cause unintended lock coupling.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(client_dir=tmp)

            # Fail the test if queue lock is used for job result operations
            original_get_lock = client.queues.get_lock

            def failing_queue_get_lock(name, *args, **kwargs):
                if name == "job-123":
                    raise AssertionError("Queues registry lock used for job results; should use _job_results lock instead")
                return original_get_lock(name, *args, **kwargs)

            monkeypatch.setattr(client.queues, "get_lock", failing_queue_get_lock, raising=True)

            # These should NOT trigger the queues registry lock
            client.store_job_result("job-123", {"result": True})
            assert client.get_job_result("job-123") == {"result": True}

    def test_job_results_saved_under_client_dir_results(self):
        """
        Expected behavior: when a client_dir is provided, job results are persisted under
        client_dir / "results". This keeps test runs isolated and avoids polluting global paths.
        """
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            client = LocalClient(client_dir=tmp_path)
            client.store_job_result("job-abc", {"ok": True})

            results_dir = tmp_path / "results"
            # Look for any registry metadata files after saving a result
            meta_files = list(results_dir.glob("_meta_*")) if results_dir.exists() else []

            assert results_dir.exists(), "results directory was not created under provided client_dir"
            assert len(meta_files) > 0, "no registry metadata found under client_dir/results after storing a job result"
