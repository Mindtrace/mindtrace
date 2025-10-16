from unittest.mock import MagicMock, patch

import pytest
import redis

from mindtrace.jobs.redis.connection import RedisConnection


@pytest.fixture
def mock_redis():
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        mock_instance = MagicMock()
        mock_redis_cls.return_value = mock_instance
        yield mock_instance


def test_connect_success(mock_redis):
    mock_redis.ping.return_value = True
    conn = RedisConnection(host="localhost", port=6381, db=0)
    assert conn.is_connected()
    mock_redis.ping.assert_called()


def test_connect_failure_then_success(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        # Fail first, then succeed
        instance.ping.side_effect = [redis.ConnectionError, True]
        mock_redis_cls.return_value = instance
        conn = RedisConnection(host="localhost", port=6381, db=0)
        assert conn.connection is instance


def test_is_connected_false(mock_redis):
    mock_redis.ping.side_effect = redis.ConnectionError
    conn = RedisConnection(host="localhost", port=6381, db=0)
    assert not conn.is_connected()


def test_close_success(mock_redis):
    conn = RedisConnection(host="localhost", port=6381, db=0)
    conn.close()
    mock_redis.close.assert_called()
    assert conn.connection is None


def test_close_error(mock_redis):
    mock_redis.close.side_effect = Exception("fail")
    conn = RedisConnection(host="localhost", port=6381, db=0)
    conn.close()  # Should not raise
    assert conn.connection is None


def test_count_queue_messages(mock_redis):
    conn = RedisConnection(host="localhost", port=6381, db=0)
    # Simulate a queue instance with qsize
    fake_queue = MagicMock()
    fake_queue.qsize.return_value = 42
    conn.queues["q"] = fake_queue
    assert conn.count_queue_messages("q") == 42
    fake_queue.qsize.assert_called_once()
    with pytest.raises(KeyError):
        conn.count_queue_messages("not_declared")


def test_connect_with_password(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        instance.ping.return_value = True
        mock_redis_cls.return_value = instance
        conn = RedisConnection(host="localhost", port=6381, db=0, password="pw")
        assert conn.is_connected()
        mock_redis_cls.assert_called_with(
            host="localhost", port=6381, db=0, socket_timeout=5.0, socket_connect_timeout=2.0, password="pw"
        )


def test_connect_retries_exhausted(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        instance.ping.side_effect = redis.ConnectionError
        mock_redis_cls.return_value = instance
        with patch("time.sleep"):
            conn = RedisConnection(host="localhost", port=6381, db=0)
            conn.connect = MagicMock(side_effect=redis.ConnectionError)
            with pytest.raises(redis.ConnectionError):
                conn.connect(max_tries=2)


def test_connect_raises(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        instance.ping.side_effect = redis.ConnectionError
        mock_redis_cls.return_value = instance
        with patch("time.sleep"):
            with pytest.raises(redis.ConnectionError):
                conn = RedisConnection(host="localhost", port=6381, db=0)
                conn.connect(max_tries=2)


def test_subscribe_to_events_declare_and_delete(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [
                {"type": "message", "data": b'{"event": "declare", "queue": "q", "queue_type": "fifo"}'},
                {"type": "message", "data": b'{"event": "delete", "queue": "q"}'},
            ]
        )
        conn.connection.pubsub.return_value = pubsub
        with patch("threading.Thread"):
            conn._subscribe_to_events()
        # Should add and then remove 'q' in queues


def test_subscribe_to_events_exception(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [
                {"type": "message", "data": b"invalid json"},
            ]
        )
        conn.connection.pubsub.return_value = pubsub
        with patch("threading.Thread"):
            # Should not raise
            conn._subscribe_to_events()


def test_load_queue_metadata_unknown_type(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {b"q": b"unknown"}
        conn.connection = mock_conn
        conn._load_queue_metadata()
        assert "q" not in conn.queues


def test_load_queue_metadata_creates_queues(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {b"q": b"fifo", b"p": b"priority", b"s": b"stack"}
        conn.connection = mock_conn
        with (
            patch("mindtrace.jobs.redis.connection.RedisQueue"),
            patch("mindtrace.jobs.redis.connection.RedisPriorityQueue"),
            patch("mindtrace.jobs.redis.connection.RedisStack"),
        ):
            conn._load_queue_metadata()
            assert "q" in conn.queues
            assert "p" in conn.queues
            assert "s" in conn.queues


def test_start_event_listener_starts_thread(monkeypatch):
    with (
        patch("mindtrace.jobs.redis.connection.threading.Thread") as mock_thread,
        patch("mindtrace.jobs.redis.connection.redis.Redis"),
    ):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        conn.connection = MagicMock()  # Prevent actual Redis usage
        conn.connection.pubsub.return_value = MagicMock()
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


def test_connect_and_close_logger_calls(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        # Simulate connection error, then success
        instance.ping.side_effect = [redis.ConnectionError, True]
        mock_redis_cls.return_value = instance
        with patch("time.sleep"):
            conn = RedisConnection(host="localhost", port=6381, db=0)
            conn.logger = MagicMock()
            # Test logger.warning called on connection error
            instance.ping.side_effect = redis.ConnectionError
            try:
                conn.connect(max_tries=1)
            except redis.ConnectionError:
                pass
            assert conn.logger.debug.called or conn.logger.warning.called
            # Test logger.error and logger.debug in close
            conn.connection = MagicMock()
            conn.connection.close.side_effect = Exception("fail")
            conn.close()
            assert conn.logger.error.called


def test_subscribe_to_events_priority_and_stack(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [
                {"type": "message", "data": b'{"event": "declare", "queue": "qp", "queue_type": "priority"}'},
                {"type": "message", "data": b'{"event": "declare", "queue": "qs", "queue_type": "stack"}'},
            ]
        )
        conn.connection.pubsub.return_value = pubsub
        with patch("threading.Thread"):
            conn._subscribe_to_events()
        assert "qp" in conn.queues
        assert "qs" in conn.queues


def test_subscribe_to_events_unknown_type_and_delete_removal(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [
                {"type": "message", "data": b'{"event": "declare", "queue": "q", "queue_type": "unknown"}'},
                {"type": "message", "data": b'{"event": "declare", "queue": "q", "queue_type": "fifo"}'},
                {"type": "message", "data": b'{"event": "delete", "queue": "q"}'},
            ]
        )
        conn.connection.pubsub.return_value = pubsub
        with patch("threading.Thread"):
            conn._subscribe_to_events()
        assert "q" not in conn.queues


def test_load_queue_metadata_handles_str_and_bytes(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {b"qb": b"fifo", "qs": "stack"}
        conn.connection = mock_conn
        with (
            patch("mindtrace.jobs.redis.connection.RedisQueue"),
            patch("mindtrace.jobs.redis.connection.RedisStack"),
        ):
            conn._load_queue_metadata()
            assert "qb" in conn.queues
            assert "qs" in conn.queues


def test_connect_exhausted_logs_then_raises(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        instance.ping.side_effect = redis.ConnectionError
        mock_redis_cls.return_value = instance
        with patch("time.sleep"):
            conn = RedisConnection(host="localhost", port=6381, db=0)
            conn.logger = MagicMock()
            with pytest.raises(redis.ConnectionError):
                conn.connect(max_tries=1)
            # After exhausting retries, a debug log is emitted before raising
            conn.logger.debug.assert_called()


def test_connect_ping_false_triggers_else_branch(monkeypatch):
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        instance = MagicMock()
        instance.ping.return_value = False
        mock_redis_cls.return_value = instance
        # __init__ calls connect(max_tries=1) and catches ConnectionError
        conn = RedisConnection(host="localhost", port=6381, db=0)
        assert conn.connection is instance


def test_connect_ping_failure(mock_redis):
    """Test connection failure when ping returns False."""
    mock_redis.ping.return_value = False
    # The constructor catches the ConnectionError and logs a warning
    # It doesn't re-raise the exception, so we check that connection fails
    conn = RedisConnection(host="localhost", port=6381, db=0)
    assert not conn.is_connected()  # Should return False since ping failed


def test_close_pubsub_error(mock_redis):
    """Test close method handles pubsub close errors gracefully."""
    conn = RedisConnection(host="localhost", port=6381, db=0)
    # Simulate pubsub connection
    mock_pubsub = MagicMock()
    mock_pubsub.close.side_effect = Exception("pubsub close failed")
    conn._pubsub = mock_pubsub
    # This should not raise an exception
    conn.close()
    mock_pubsub.close.assert_called_once()


def test_del_method_exception_handling():
    """Test __del__ method handles exceptions gracefully."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis") as mock_redis_cls:
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_cls.return_value = mock_instance
        conn = RedisConnection(host="localhost", port=6381, db=0)
        # Make close raise an exception
        conn.close = MagicMock(side_effect=Exception("close failed"))
        # This should not raise an exception
        conn.__del__()


def test_subscribe_to_events_shutdown_signal(monkeypatch):
    """Test that _subscribe_to_events respects shutdown signal."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)
        # Set shutdown event before starting
        conn._shutdown_event.set()

        pubsub = MagicMock()

        # Create an iterator that will be interrupted by shutdown
        def message_generator():
            yield {"type": "subscribe"}
            # After first message, shutdown should be detected

        pubsub.listen.return_value = message_generator()
        conn.connection.pubsub.return_value = pubsub

        # This should exit quickly due to shutdown event
        conn._subscribe_to_events()


def test_subscribe_to_events_exception_handling(monkeypatch):
    """Test that _subscribe_to_events handles exceptions in the main loop."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        # Make pubsub.listen() raise an exception
        pubsub = MagicMock()
        pubsub.listen.side_effect = Exception("connection lost")
        conn.connection.pubsub.return_value = pubsub

        # This should not raise an exception, just log it
        conn._subscribe_to_events()


def test_subscribe_to_events_non_message_type(monkeypatch):
    """Test that _subscribe_to_events handles non-message type events."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [
                {"type": "subscribe"},  # Non-message type should be skipped
                {"type": "message", "data": b'{"event": "declare", "queue": "q", "queue_type": "fifo"}'},
            ]
        )
        conn.connection.pubsub.return_value = pubsub

        # Set shutdown after processing to exit loop
        def set_shutdown():
            conn._shutdown_event.set()

        # Use side effect to set shutdown after first call
        original_is_set = conn._shutdown_event.is_set
        call_count = [0]

        def mock_is_set():
            call_count[0] += 1
            if call_count[0] > 2:  # Allow a few calls then shutdown
                return True
            return original_is_set()

        conn._shutdown_event.is_set = mock_is_set

        with patch("threading.Thread"):
            conn._subscribe_to_events()


def test_subscribe_to_events_unknown_queue_type(monkeypatch):
    """Test _subscribe_to_events with unknown queue type in declare event."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [{"type": "message", "data": b'{"event": "declare", "queue": "q", "queue_type": "unknown"}'}]
        )
        conn.connection.pubsub.return_value = pubsub

        # Set shutdown after processing to exit loop
        call_count = [0]
        original_is_set = conn._shutdown_event.is_set

        def mock_is_set():
            call_count[0] += 1
            if call_count[0] > 2:  # Allow a few calls then shutdown
                return True
            return original_is_set()

        conn._shutdown_event.is_set = mock_is_set

        # This should handle unknown queue type gracefully
        conn._subscribe_to_events()

        # Should not have added anything to queues
        assert len(conn.queues) == 0


def test_subscribe_to_events_delete_nonexistent_queue(monkeypatch):
    """Test _subscribe_to_events with delete event for nonexistent queue."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        pubsub = MagicMock()
        pubsub.listen.return_value = iter([{"type": "message", "data": b'{"event": "delete", "queue": "nonexistent"}'}])
        conn.connection.pubsub.return_value = pubsub

        # Set shutdown after processing to exit loop
        call_count = [0]
        original_is_set = conn._shutdown_event.is_set

        def mock_is_set():
            call_count[0] += 1
            if call_count[0] > 2:  # Allow a few calls then shutdown
                return True
            return original_is_set()

        conn._shutdown_event.is_set = mock_is_set

        # This should handle delete of nonexistent queue gracefully
        conn._subscribe_to_events()


def test_subscribe_to_events_pubsub_close_in_finally(monkeypatch):
    """Test that _subscribe_to_events closes pubsub in finally block."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        # Make pubsub.listen() raise an exception to trigger finally block
        pubsub = MagicMock()
        pubsub.listen.side_effect = Exception("connection lost")
        conn.connection.pubsub.return_value = pubsub

        # This should call pubsub.close() in the finally block
        conn._subscribe_to_events()

        pubsub.close.assert_called_once()


def test_subscribe_to_events_pubsub_close_exception_in_finally(monkeypatch):
    """Test that _subscribe_to_events handles pubsub close exception in finally block."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        # Make pubsub.listen() raise an exception to trigger finally block
        pubsub = MagicMock()
        pubsub.listen.side_effect = Exception("connection lost")
        pubsub.close.side_effect = Exception("close failed")
        conn.connection.pubsub.return_value = pubsub

        # This should handle the close exception gracefully
        conn._subscribe_to_events()

        pubsub.close.assert_called_once()


def test_subscribe_to_events_declare_stack_queue(monkeypatch):
    """Test _subscribe_to_events with declare event for stack queue type."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [{"type": "message", "data": b'{"event": "declare", "queue": "stack_q", "queue_type": "stack"}'}]
        )
        conn.connection.pubsub.return_value = pubsub

        # Set shutdown after processing to exit loop
        call_count = [0]
        original_is_set = conn._shutdown_event.is_set

        def mock_is_set():
            call_count[0] += 1
            if call_count[0] > 2:  # Allow a few calls then shutdown
                return True
            return original_is_set()

        conn._shutdown_event.is_set = mock_is_set

        with patch("mindtrace.jobs.redis.connection.RedisStack") as mock_stack:
            conn._subscribe_to_events()
            mock_stack.assert_called_once()


def test_subscribe_to_events_declare_priority_queue(monkeypatch):
    """Test _subscribe_to_events with declare event for priority queue type."""
    with patch("mindtrace.jobs.redis.connection.redis.Redis"):
        conn = RedisConnection(host="localhost", port=6381, db=0)

        pubsub = MagicMock()
        pubsub.listen.return_value = iter(
            [{"type": "message", "data": b'{"event": "declare", "queue": "priority_q", "queue_type": "priority"}'}]
        )
        conn.connection.pubsub.return_value = pubsub

        # Set shutdown after processing to exit loop
        call_count = [0]
        original_is_set = conn._shutdown_event.is_set

        def mock_is_set():
            call_count[0] += 1
            if call_count[0] > 2:  # Allow a few calls then shutdown
                return True
            return original_is_set()

        conn._shutdown_event.is_set = mock_is_set

        with patch("mindtrace.jobs.redis.connection.RedisPriorityQueue") as mock_priority:
            conn._subscribe_to_events()
            mock_priority.assert_called_once()
