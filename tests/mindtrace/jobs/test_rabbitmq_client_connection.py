import json
import time
import uuid
from unittest import mock

import pika
import pytest
import pydantic

from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.rabbitmq.client import RabbitMQClient


pytestmark = pytest.mark.rabbitmq  # ensure these tests are only executed when RabbitMQ is available


class DummyModel(pydantic.BaseModel):
    value: str


@pytest.fixture(scope="module")
def rabbitmq_connection():
    conn = RabbitMQConnection(host="localhost", port=5672, username="user", password="password")
    try:
        conn.connect()
    except Exception:  # pragma: no cover – skip tests if broker not reachable
        pytest.skip("RabbitMQ broker not available on localhost:5672 with user/password credentials")
    yield conn
    conn.close()


@pytest.fixture
def rabbitmq_client(rabbitmq_connection):
    client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
    yield client
    # cleanup any declared resources that may have been left over
    try:
        client.channel.close()
    except Exception:
        pass
    client.connection.close()


def unique_name(base: str) -> str:
    """Utility to generate unique names to avoid collisions between tests."""
    return f"{base}_{uuid.uuid4().hex[:8]}"


class TestRabbitMQConnection:
    def test_connection_cycle(self, rabbitmq_connection):
        """Basic connect / is_connected / close cycle."""
        assert rabbitmq_connection.is_connected()
        channel = rabbitmq_connection.get_channel()
        assert channel is not None and channel.is_open
        rabbitmq_connection.close()
        assert not rabbitmq_connection.is_connected()

    def test_retry_logic(self, monkeypatch):
        """Force two connection failures then success to exercise retry loop."""
        attempts = {"n": 0}

        def fake_blocking_conn(*_a, **_kw):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise pika.exceptions.AMQPConnectionError("boom")
            return mock.Mock(is_open=True)

        monkeypatch.setattr("mindtrace.jobs.rabbitmq.connection.BlockingConnection", fake_blocking_conn)
        conn = RabbitMQConnection(host="localhost", port=5672, username="user", password="password")
        conn.connect()
        assert attempts["n"] == 3  # retried until third attempt
        assert conn.is_connected()
        conn.close()

    def test_retry_exhausted(self, monkeypatch):
        """Test maximum retry exhaustion."""
        def always_fail(*_a, **_kw):
            raise pika.exceptions.AMQPConnectionError("always fail")

        monkeypatch.setattr("mindtrace.jobs.rabbitmq.connection.BlockingConnection", always_fail)
        conn = RabbitMQConnection(host="localhost", port=5672, username="user", password="password")
        
        with pytest.raises(pika.exceptions.AMQPConnectionError, match="Failed to connect"):
            conn.connect()

    def test_get_channel_when_not_connected(self):
        """Test get_channel returns None when not connected."""
        conn = RabbitMQConnection(host="localhost", port=5672, username="user", password="password")
        # Don't connect
        assert conn.get_channel() is None

    def test_close_when_not_connected(self):
        """Test close when not connected (should not crash)."""
        conn = RabbitMQConnection(host="localhost", port=5672, username="user", password="password")
        # Don't connect, just try to close
        conn.close()  # Should not crash
        assert not conn.is_connected()


class TestRabbitMQClient:
    def test_exchange_and_queue_declaration(self, rabbitmq_client):
        exchange = unique_name("ex"); queue = unique_name("q")
        # declare exchange first time -> success
        result1 = rabbitmq_client.declare_exchange(exchange=exchange)
        assert result1["status"] == "success"
        # second call – already exists branch
        result2 = rabbitmq_client.declare_exchange(exchange=exchange)
        assert "already exists" in result2["message"]

        # queue declaration bound to exchange
        res_q1 = rabbitmq_client.declare_queue(queue, exchange=exchange)
        assert res_q1["status"] == "success"
        # declaring again hits already-exists branch
        res_q2 = rabbitmq_client.declare_queue(queue)
        assert "already exists" in res_q2["message"]

    def test_declare_exchange_error(self, rabbitmq_client, monkeypatch):
        """Test exchange declaration error path."""
        def raise_error(*args, **kwargs):
            raise Exception("test error")
        
        # Mock to force error in declare_exchange
        monkeypatch.setattr(rabbitmq_client.channel, "exchange_declare", raise_error)
        
        with pytest.raises(RuntimeError, match="Could not declare exchange"):
            rabbitmq_client.declare_exchange(exchange="test_ex")

    def test_declare_queue_without_exchange(self, rabbitmq_client):
        """Test queue declaration without providing exchange (uses default)."""
        queue = unique_name("default_q")
        result = rabbitmq_client.declare_queue(queue, force=True)
        assert result["status"] == "success"

    def test_declare_queue_with_priority(self, rabbitmq_client):
        """Test queue declaration with max_priority."""
        queue = unique_name("priority_q")
        result = rabbitmq_client.declare_queue(queue, max_priority=10, force=True)
        assert result["status"] == "success"

    def test_declare_queue_nonexistent_exchange_without_force(self, rabbitmq_client):
        """Test queue declaration with non-existent exchange without force."""
        queue = unique_name("err_q")
        nonexistent_exchange = unique_name("no_ex")
        
        with pytest.raises(ValueError, match="Use force=True"):
            rabbitmq_client.declare_queue(queue, exchange=nonexistent_exchange, force=False)

    def test_declare_queue_unexpected_error(self, rabbitmq_client, monkeypatch):
        """Test unexpected error in queue declaration."""
        def raise_unexpected(*args, **kwargs):
            raise Exception("unexpected error")
        
        # Force queue_declare to fail with unexpected error
        original_queue_declare = rabbitmq_client.channel.queue_declare
        def patched_queue_declare(*args, **kwargs):
            if kwargs.get("passive"):
                raise pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
            else:
                raise Exception("unexpected error")
        
        # Mock exchange_declare to succeed for the passive check
        def patched_exchange_declare(*args, **kwargs):
            return True  # Simulate success
            
        # Mock get_channel to return the same channel
        def patched_get_channel():
            return rabbitmq_client.channel
        
        monkeypatch.setattr(rabbitmq_client.channel, "queue_declare", patched_queue_declare)
        monkeypatch.setattr(rabbitmq_client.channel, "exchange_declare", patched_exchange_declare)
        monkeypatch.setattr(rabbitmq_client.connection, "get_channel", patched_get_channel)
        
        result = rabbitmq_client.declare_queue("error_queue")
        assert result["status"] == "error"
        assert "unexpected error" in result["message"]

    def test_publish_receive_and_cleanup(self, rabbitmq_client):
        queue_name = unique_name("testq")
        rabbitmq_client.declare_queue(queue_name, force=True)

        payload = DummyModel(value="hello")
        job_id = rabbitmq_client.publish(queue_name, payload)
        assert isinstance(job_id, str) and len(job_id) > 0

        msg = rabbitmq_client.receive_message(queue_name, block=True, timeout=2)
        assert msg == payload.model_dump()

        # queue should now be empty – receive non-blocking should say no message
        empty_resp = rabbitmq_client.receive_message(queue_name, block=False)
        assert empty_resp["status"] == "error"

        # cleanup helpers
        rabbitmq_client.clean_queue(queue_name)
        assert rabbitmq_client.count_queue_messages(queue_name) == 0
        rabbitmq_client.delete_queue(queue_name)

    def test_publish_error_paths(self, rabbitmq_client, monkeypatch):
        """Test various publish error paths."""
        queue_name = unique_name("errq")
        rabbitmq_client.declare_queue(queue_name, force=True)
        payload = DummyModel(value="fail")

        # Test UnroutableError
        def raise_unroutable(*args, **kwargs):
            raise pika.exceptions.UnroutableError("no route")
        monkeypatch.setattr(rabbitmq_client.channel, "basic_publish", raise_unroutable)
        with pytest.raises(pika.exceptions.UnroutableError):
            rabbitmq_client.publish(queue_name, payload)

        # Test ChannelClosedByBroker
        def raise_channel_closed(*args, **kwargs):
            raise pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
        monkeypatch.setattr(rabbitmq_client.channel, "basic_publish", raise_channel_closed)
        with pytest.raises(pika.exceptions.ChannelClosedByBroker):
            rabbitmq_client.publish(queue_name, payload)

        # Test ConnectionClosedByBroker
        def raise_connection_closed(*args, **kwargs):
            raise pika.exceptions.ConnectionClosedByBroker(320, "CONNECTION_FORCED")
        monkeypatch.setattr(rabbitmq_client.channel, "basic_publish", raise_connection_closed)
        with pytest.raises(pika.exceptions.ConnectionClosedByBroker):
            rabbitmq_client.publish(queue_name, payload)

        # Test generic Exception
        def raise_generic(*args, **kwargs):
            raise Exception("generic error")
        monkeypatch.setattr(rabbitmq_client.channel, "basic_publish", raise_generic)
        with pytest.raises(Exception, match="generic error"):
            rabbitmq_client.publish(queue_name, payload)

    def test_receive_timeout(self, rabbitmq_client):
        queue_name = unique_name("timeoutq")
        rabbitmq_client.declare_queue(queue_name, force=True)
        start = time.time()
        resp = rabbitmq_client.receive_message(queue_name, block=True, timeout=0.5)
        elapsed = time.time() - start
        # should respect timeout and return error dict
        assert elapsed >= 0.5
        assert resp["status"] == "error"

    def test_receive_reconnection(self, rabbitmq_client):
        """Test receive_message reconnection logic."""
        queue_name = unique_name("reconn_q")
        rabbitmq_client.declare_queue(queue_name, force=True)
        
        # Simulate disconnected state
        rabbitmq_client.connection.connection = None
        rabbitmq_client.channel = None
        
        # Should reconnect automatically
        resp = rabbitmq_client.receive_message(queue_name, block=False)
        assert resp["status"] == "error"  # No message, but connection worked

    def test_count_exchanges(self, rabbitmq_client):
        """Test count_exchanges method."""
        exchange = unique_name("count_ex")
        rabbitmq_client.declare_exchange(exchange=exchange)
        
        result = rabbitmq_client.count_exchanges(exchange=exchange)
        assert result is not None

    def test_delete_exchange(self, rabbitmq_client):
        """Test delete_exchange method."""
        exchange = unique_name("del_ex")
        rabbitmq_client.declare_exchange(exchange=exchange)
        
        result = rabbitmq_client.delete_exchange(exchange=exchange)
        assert result["status"] == "success"

    def test_error_handling_with_channel_closed(self, rabbitmq_client, monkeypatch):
        """Test error handling when channel operations fail."""
        queue_name = unique_name("err_clean_q")
        
        # Test clean_queue error
        def raise_channel_error(*args, **kwargs):
            raise pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
        
        monkeypatch.setattr(rabbitmq_client.channel, "queue_purge", raise_channel_error)
        with pytest.raises(ConnectionError, match="Could not clean queue"):
            rabbitmq_client.clean_queue(queue_name)

        # Test delete_queue error
        monkeypatch.setattr(rabbitmq_client.channel, "queue_delete", raise_channel_error)
        with pytest.raises(ConnectionError, match="Could not delete queue"):
            rabbitmq_client.delete_queue(queue_name)

        # Test count_queue_messages error
        monkeypatch.setattr(rabbitmq_client.channel, "queue_declare", raise_channel_error)
        with pytest.raises(ConnectionError, match="Could not count messages"):
            rabbitmq_client.count_queue_messages(queue_name)

        # Test count_exchanges error
        monkeypatch.setattr(rabbitmq_client.channel, "exchange_declare", raise_channel_error)
        with pytest.raises(ConnectionError, match="Could not count exchanges"):
            rabbitmq_client.count_exchanges(exchange="test")

        # Test delete_exchange error
        monkeypatch.setattr(rabbitmq_client.channel, "exchange_delete", raise_channel_error)
        with pytest.raises(ConnectionError, match="Could not delete exchange"):
            rabbitmq_client.delete_exchange(exchange="test")

    def test_move_to_dlq(self, rabbitmq_client):
        """Test move_to_dlq method (currently a pass)."""
        payload = DummyModel(value="test")
        # Should not raise any errors
        rabbitmq_client.move_to_dlq("source", "dlq", payload, "error details")

    def test_declare_queue_force_create_exchange(self, rabbitmq_client):
        """Test queue declaration with force=True to create new exchange."""
        queue = unique_name("force_q")
        new_exchange = unique_name("new_ex")
        
        # This should create the exchange since force=True
        result = rabbitmq_client.declare_queue(queue, exchange=new_exchange, force=True)
        assert result["status"] == "success"
        assert "newly declared exchange" in result["message"]
        
        # Clean up
        rabbitmq_client.delete_queue(queue)
        rabbitmq_client.delete_exchange(exchange=new_exchange)

    def test_declare_queue_first_call_unexpected_error(self, rabbitmq_client, monkeypatch):
        """Test unexpected error in the first queue_declare call."""
        def raise_generic_error(*args, **kwargs):
            raise Exception("first call error")
        
        monkeypatch.setattr(rabbitmq_client.channel, "queue_declare", raise_generic_error)
        
        result = rabbitmq_client.declare_queue("test_queue")
        assert result["status"] == "error"
        assert "Unexpected error" in result["message"]
        assert "first call error" in result["message"]

    def test_receive_message_error_handling(self, rabbitmq_client, monkeypatch):
        """Test error handling in receive_message."""
        queue_name = unique_name("err_recv_q")
        
        def raise_receive_error(*args, **kwargs):
            raise Exception("receive error")
        
        monkeypatch.setattr(rabbitmq_client.channel, "basic_get", raise_receive_error)
        
        with pytest.raises(RuntimeError, match="Error receiving message"):
            rabbitmq_client.receive_message(queue_name, block=False)

    def test_declare_exchange_inner_exception(self, rabbitmq_client, monkeypatch):
        """Test exception in the inner try block of declare_exchange."""
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call (passive check) raises ChannelClosedByBroker
                raise pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
            else:
                # Second call (actual declaration) raises generic exception
                raise Exception("inner exception")
        
        monkeypatch.setattr(rabbitmq_client.channel, "exchange_declare", side_effect)
        monkeypatch.setattr(rabbitmq_client.connection, "get_channel", lambda: rabbitmq_client.channel)
        
        with pytest.raises(RuntimeError, match="Could not declare exchange"):
            rabbitmq_client.declare_exchange(exchange="test_ex")

    def test_move_to_dlq_coverage(self, rabbitmq_client):
        """Test move_to_dlq method to ensure it's covered."""
        payload = DummyModel(value="test")
        # This method currently just passes, but we want to cover it
        result = rabbitmq_client.move_to_dlq("source", "dlq", payload, "error details")
        # Since it's a pass statement, it should return None
        assert result is None

    def test_receive_message_successful_non_blocking(self, rabbitmq_client, monkeypatch):
        """Test successful message retrieval in non-blocking mode."""
        # Create a mock method frame and body
        mock_method_frame = mock.Mock()
        mock_header_frame = mock.Mock()
        test_message = {"id": "test123", "data": "test_data"}
        mock_body = json.dumps(test_message).encode("utf-8")
        
        def mock_basic_get(*args, **kwargs):
            return mock_method_frame, mock_header_frame, mock_body
        
        monkeypatch.setattr(rabbitmq_client.channel, "basic_get", mock_basic_get)
        
        result = rabbitmq_client.receive_message("test_queue", block=False)
        
        assert result == test_message 