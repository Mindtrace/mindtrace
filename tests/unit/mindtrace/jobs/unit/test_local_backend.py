import time

import pytest

from mindtrace.jobs.local.client import LocalClient


class TestLocalBroker:
    """Tests for LocalBroker backend."""

    def setup_method(self):
        pass

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
        """Test that LocalBroker raises NotImplementedError for exchange methods."""
        broker = temp_local_client
        with pytest.raises(NotImplementedError):
            broker.declare_exchange(exchange="test_exchange")

        with pytest.raises(NotImplementedError):
            broker.delete_exchange(exchange="test_exchange")

        with pytest.raises(NotImplementedError):
            broker.count_exchanges()
