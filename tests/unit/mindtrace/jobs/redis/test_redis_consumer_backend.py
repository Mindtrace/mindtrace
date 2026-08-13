from queue import Empty
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.jobs import ConsumerFailurePolicy
from mindtrace.jobs.redis.consumer_backend import RedisConsumerBackend


@pytest.fixture
def backend():
    with patch("mindtrace.jobs.redis.consumer_backend.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        backend = RedisConsumerBackend("q", MagicMock(), "localhost", 6379, 0)
        backend.connection = mock_conn
        yield backend, mock_conn


@pytest.mark.parametrize(
    "failure_policy",
    [ConsumerFailurePolicy.REQUEUE, ConsumerFailurePolicy.DEAD_LETTER],
)
def test_rejects_unsupported_failure_policies(failure_policy):
    with pytest.raises(
        NotImplementedError,
        match=f"Redis consumer backend does not support failure policy '{failure_policy.value}'",
    ):
        RedisConsumerBackend(
            "q",
            MagicMock(),
            "localhost",
            6379,
            0,
            failure_policy=failure_policy,
        )


def test_consume_processes_messages(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=[{"id": 1}, None])
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=1, block=False)
    backend.process_message.assert_called_once_with({"id": 1})


def test_finite_consume_stops_before_polling_next_queue(backend):
    backend, _ = backend
    backend.receive_message = MagicMock(return_value={"id": 1})
    backend.process_message = MagicMock(return_value=True)

    backend.consume(num_messages=1, queues=["q1", "q2"], block=False)

    backend.receive_message.assert_called_once_with("q1", block=False, timeout=None)


def test_nonblocking_consume_checks_later_queue_before_returning(backend):
    backend, _ = backend

    def receive_message(queue, *, block, timeout):
        if queue == "q1":
            return None
        return {"id": 2}

    backend.receive_message = MagicMock(side_effect=receive_message)
    backend.process_message = MagicMock(return_value=True)

    backend.consume(num_messages=1, queues=["q1", "q2"], block=False)

    assert [call.args[0] for call in backend.receive_message.call_args_list] == ["q1", "q2"]
    backend.process_message.assert_called_once_with({"id": 2})


def test_blocking_consume_waits_after_idle_queue_sweep(backend):
    backend, _ = backend
    attempts = 0

    def receive_message(queue, *, block, timeout):
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            backend.stop()
        return None

    backend.receive_message = MagicMock(side_effect=receive_message)
    backend._stop_event.wait = MagicMock()

    backend.consume(num_messages=1, queues=["q"], block=True)

    backend._stop_event.wait.assert_called_once()


def test_stopped_entry_skips_redis_consume(backend):
    backend, _ = backend
    backend.receive_message = MagicMock(return_value={"id": 1})
    backend.logger = MagicMock()

    backend.stop()
    backend.consume(num_messages=1, block=False)

    backend.receive_message.assert_not_called()
    assert backend.stopped is True
    backend.logger.info.assert_called_once_with(
        "Consumption skipped because stop was requested; call reset() before consuming again."
    )


def test_consume_until_empty(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(block=False)
    backend.consume.assert_called_with(num_messages=1, queues=["q"], block=False)


def test_consume_until_empty_uses_bounded_nonblocking_pass(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]

    def consume_one(*, num_messages, queues, block):
        assert num_messages == 1
        assert queues == ["q"]
        assert block is False, "A drain pass must not wait for work that disappeared after the pending count."
        return 1

    backend.consume = MagicMock(side_effect=consume_one)

    backend.consume_until_empty(block=True)

    backend.consume.assert_called_once()


def test_consume_until_empty_does_not_treat_concurrent_publish_as_no_progress(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 1, 0]
    backend.consume = MagicMock(return_value=1)
    backend.logger = MagicMock()

    backend.consume_until_empty(block=False)

    assert backend.consume.call_count == 1
    assert not any("Drain stalled" in item.args[0] for item in backend.logger.error.call_args_list)


def test_consume_until_empty_aborts_when_redis_drain_makes_no_progress(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 1]
    backend.consume = MagicMock(return_value=0)
    backend.logger = MagicMock()

    backend.consume_until_empty(block=False)

    backend.consume.assert_called_once_with(num_messages=1, queues=["q"], block=False)
    assert mock_conn.count_queue_messages.call_count == 2
    backend.logger.error.assert_called_once_with("Drain stalled with 1 messages pending; aborting.")


def test_consume_until_empty_reports_stop_requested_during_redis_drain(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.return_value = 1
    backend.logger = MagicMock()

    def consume_and_stop(**_kwargs):
        backend.stop()
        return 1

    backend.consume = MagicMock(side_effect=consume_and_stop)

    backend.consume_until_empty(block=False)

    backend.consume.assert_called_once_with(num_messages=1, queues=["q"], block=False)
    mock_conn.count_queue_messages.assert_called_once_with("q")
    backend.logger.info.assert_called_once_with("Stopped draining queues after shutdown request: ['q'].")


def test_stopped_entry_skips_redis_drain(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.logger = MagicMock()
    backend.stop()

    backend.consume_until_empty(block=False)

    mock_conn.count_queue_messages.assert_not_called()
    backend.logger.info.assert_called_once_with(
        "Consumption skipped because stop was requested; call reset() before consuming again."
    )


def test_close_is_terminal_and_idempotent(backend):
    backend, mock_conn = backend

    backend.close()
    backend.close()

    assert backend.closed is True
    mock_conn.close.assert_called_once_with()
    with pytest.raises(RuntimeError, match="Consumer backend is closed"):
        backend.consume(num_messages=1, block=False)
    with pytest.raises(RuntimeError, match="Consumer backend is closed"):
        backend.consume_until_empty(block=False)
    with pytest.raises(RuntimeError, match="Consumer backend is closed"):
        backend.reset()


def test_process_message_dict_success(backend):
    backend, _ = backend
    frontend = MagicMock()
    backend.consumer_frontend = frontend
    backend.logger = MagicMock()
    msg = {"id": 123}
    assert backend.process_message(msg)
    frontend.run.assert_called_once_with(msg)


def test_process_message_dict_error(backend):
    backend, _ = backend
    frontend = MagicMock()
    frontend.run.side_effect = Exception("fail")
    backend.consumer_frontend = frontend
    backend.logger = MagicMock()
    msg = {"id": 123}
    assert not backend.process_message(msg)
    frontend.run.assert_called_once_with(msg)


def test_process_message_non_dict(backend):
    backend, _ = backend
    backend.logger = MagicMock()
    assert not backend.process_message("notadict")


def test_set_poll_timeout(backend):
    backend, _ = backend
    backend.set_poll_timeout(42)
    assert backend.poll_timeout == 42


def test_receive_message_success(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.return_value = '{"foo": "bar"}'
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    with patch("json.loads", return_value={"foo": "bar"}):
        result = backend.receive_message("q")
        assert result == {"foo": "bar"}


def test_receive_message_empty(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock(spec=["pop"])
    fake_queue.pop.side_effect = Empty
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    assert backend.receive_message("q") is None


def test_receive_message_propagates_redis_operational_failure(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock(spec=["pop"])
    fake_queue.pop.side_effect = RuntimeError("redis unavailable")
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    with pytest.raises(RuntimeError, match="redis unavailable"):
        backend.receive_message("q")


def test_blocking_consume_does_not_wait_after_removing_malformed_redis_payload(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock(spec=["pop"])
    fake_queue.pop.return_value = "not-json"
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    backend._stop_event.wait = MagicMock(side_effect=lambda _timeout: backend.stop())

    backend.consume(num_messages=1, queues="q", block=True)

    backend._stop_event.wait.assert_not_called()
    fake_queue.pop.assert_called_once()


def test_consume_rejects_negative_message_count(backend):
    backend, _ = backend
    backend.receive_message = MagicMock()

    with pytest.raises(ValueError, match="num_messages must be non-negative"):
        backend.consume(num_messages=-1, queues="q", block=False)

    backend.receive_message.assert_not_called()


def test_receive_message_queue_not_declared(backend):
    backend, mock_conn = backend
    mock_conn.queues = {}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    with pytest.raises(KeyError):
        backend.receive_message("not_declared")


def test_consume_non_block_returns_immediately_when_no_message(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(return_value=None)
    backend.logger = MagicMock()
    # Should return immediately due to not block and no message
    backend.consume(num_messages=0, queues=["q"], block=False)
    backend.receive_message.assert_called_once_with("q", block=False, timeout=None)


def test_consume_non_block_propagates_operational_exception(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=RuntimeError("redis unavailable"))
    backend.logger = MagicMock()
    with pytest.raises(RuntimeError, match="redis unavailable"):
        backend.consume(num_messages=0, queues=["q"], block=False)


def test_receive_message_uses_get_and_returns_dict(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.get.return_value = '{"foo": "bar"}'
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    result = backend.receive_message("q")
    assert result == {"foo": "bar"}


def test_receive_message_unsupported_queue_type_raises(backend):
    backend, mock_conn = backend

    # Queue instance without get/pop attributes
    class Unsupported:
        pass

    mock_conn.queues = {"q": Unsupported()}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    with pytest.raises(RuntimeError, match="does not support receiving messages"):
        backend.receive_message("q")


def test_consume_until_empty_logs_info(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(block=False)
    backend.logger.info.assert_called()


def test_process_message_non_dict_logs(backend):
    backend, _ = backend
    backend.logger = MagicMock()
    result = backend.process_message([1, 2, 3])
    assert result is False
    backend.logger.warning.assert_called()
    backend.logger.debug.assert_called()


def test_consume_finally_logs_info(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=KeyboardInterrupt)
    backend.logger = MagicMock()
    backend.consume(num_messages=1, block=True)
    backend.logger.info.assert_called()


def test_consume_no_queues_returns_immediately(backend):
    backend, _ = backend
    backend.queues = []
    backend.logger = MagicMock()
    # Should return immediately without error
    backend.consume(num_messages=1, block=False)


def test_receive_message_general_exception_propagates(backend):
    backend, mock_conn = backend

    class Bad:
        def pop(self, *a, **k):
            raise RuntimeError("boom")

    mock_conn.queues = {"q": Bad()}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    with pytest.raises(RuntimeError, match="boom"):
        backend.receive_message("q")


def test_consume_logs_when_processing_and_increments(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(return_value={"id": 1})
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=1, block=True)
    backend.logger.debug.assert_any_call("Received message from queue 'q': processing 1")


def test_consume_until_empty_info_log_message(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(block=False)
    backend.logger.info.assert_called_with("Stopped consuming messages from queues: ['q'] (queues empty).")


def test_consume_normalizes_string_queues_and_handles_keyboardinterrupt(backend):
    backend, _ = backend
    backend.receive_message = MagicMock(side_effect=KeyboardInterrupt)
    backend.logger = MagicMock()
    # Pass queues as a string to trigger normalization branch
    backend.consume(num_messages=1, queues="q", block=True)
    backend.logger.info.assert_called()


def test_consume_exception_block_true_propagates_without_waiting(backend):
    backend, _ = backend
    backend.logger = MagicMock()
    backend.receive_message = MagicMock(side_effect=RuntimeError("redis unavailable"))
    backend._stop_event.wait = MagicMock(
        side_effect=AssertionError("A failed queue sweep must not enter the blocking wait path.")
    )

    with pytest.raises(RuntimeError, match="redis unavailable"):
        backend.consume(num_messages=1, queues="q", block=True)

    backend._stop_event.wait.assert_not_called()


def test_consume_until_empty_normalizes_string_queue(backend):
    backend, mock_conn = backend
    backend.logger = MagicMock()
    backend.consume = MagicMock()
    # Make sure string queues normalize
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume_until_empty(queues="q", block=False)
    backend.consume.assert_called_with(num_messages=1, queues=["q"], block=False)


def test_receive_message_get_raises_empty_returns_none(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.get.side_effect = Empty
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    assert backend.receive_message("q") is None


def test_del_handles_exceptions_gracefully(backend):
    """Test that __del__ method handles exceptions gracefully."""
    backend, mock_conn = backend
    # Make close() raise an exception
    backend.close = MagicMock(side_effect=Exception("close failed"))
    # __del__ should catch the exception and not raise
    try:
        backend.__del__()
    except Exception:
        pytest.fail("__del__ should catch all exceptions from close()")
    # Verify close was called
    backend.close.assert_called_once()
