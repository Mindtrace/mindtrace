"""Unit tests for ``mindtrace.agents.execution.rabbitmq.RabbitMQTaskQueue``.

``aio_pika`` is an optional dependency; a lightweight stub is registered so this
module can be imported in the default unit-test environment.
"""

from __future__ import annotations

import asyncio
import pickle
import sys
import types
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_aio = types.ModuleType("aio_pika")
_aio_abc = types.ModuleType("aio_pika.abc")


class _StubMessage:
    def __init__(self, body: bytes = b"", correlation_id: str | None = None, reply_to: str | None = None):
        self.body = body
        self.correlation_id = correlation_id
        self.reply_to = reply_to


_aio.Message = _StubMessage
_aio.connect_robust = AsyncMock()
sys.modules.setdefault("aio_pika", _aio)
sys.modules.setdefault("aio_pika.abc", _aio_abc)

from mindtrace.agents.execution._queue import AgentTask, TaskStatus
from mindtrace.agents.execution.rabbitmq import RabbitMQTaskQueue


@pytest.fixture
def queue() -> RabbitMQTaskQueue:
    return RabbitMQTaskQueue("amqp://guest:guest@localhost/")


@pytest.mark.asyncio
async def test_submit_publishes_task_and_sets_running(queue: RabbitMQTaskQueue) -> None:
    mock_channel = AsyncMock()
    mock_callback_q = AsyncMock()
    mock_callback_q.name = "cbq"

    async def ensure() -> tuple:
        return mock_channel, mock_callback_q

    with patch.object(RabbitMQTaskQueue, "_ensure_connected", side_effect=ensure):
        task = AgentTask(agent_name="agent-a", input="hi")
        task_id = await queue.submit(task)
        assert await queue.status(task_id) == TaskStatus.RUNNING
        mock_channel.default_exchange.publish.assert_awaited()
        msg = mock_channel.default_exchange.publish.call_args[0][0]
        assert pickle.loads(msg.body) == task
        assert msg.reply_to == "cbq"
        assert msg.correlation_id == task_id


@pytest.mark.asyncio
async def test_get_result_unknown_task(queue: RabbitMQTaskQueue) -> None:
    with pytest.raises(KeyError, match="Unknown task_id"):
        await queue.get_result("not-there")


@pytest.mark.asyncio
async def test_cancel_marks_failed(queue: RabbitMQTaskQueue) -> None:
    mock_channel = AsyncMock()
    mock_callback_q = AsyncMock()
    mock_callback_q.name = "cbq"

    async def ensure() -> tuple:
        return mock_channel, mock_callback_q

    with patch.object(RabbitMQTaskQueue, "_ensure_connected", side_effect=ensure):
        task_id = await queue.submit(AgentTask(agent_name="x", input="y"))
        await queue.cancel(task_id)
        assert await queue.status(task_id) == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_status_unknown_defaults_pending(queue: RabbitMQTaskQueue) -> None:
    assert await queue.status("missing") == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_ensure_connected_reuses_open_connection(queue: RabbitMQTaskQueue) -> None:
    import aio_pika

    mock_conn = AsyncMock()
    mock_conn.is_closed = False
    mock_ch = AsyncMock()
    mock_cq = AsyncMock()
    mock_cq.consume = AsyncMock()
    mock_ch.declare_queue = AsyncMock(return_value=mock_cq)
    mock_conn.channel = AsyncMock(return_value=mock_ch)
    aio_pika.connect_robust = AsyncMock(return_value=mock_conn)

    c1, q1 = await queue._ensure_connected()
    c2, q2 = await queue._ensure_connected()
    assert c1 is c2 and q1 is q2
    aio_pika.connect_robust.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_connected_reopens_when_closed(queue: RabbitMQTaskQueue) -> None:
    import aio_pika

    mock_conn_a = AsyncMock()
    mock_conn_a.is_closed = False
    mock_conn_b = AsyncMock()
    mock_conn_b.is_closed = False

    mock_ch = AsyncMock()
    mock_cq = AsyncMock()
    mock_cq.consume = AsyncMock()
    mock_ch.declare_queue = AsyncMock(return_value=mock_cq)
    mock_conn_a.channel = AsyncMock(return_value=mock_ch)
    mock_conn_b.channel = AsyncMock(return_value=mock_ch)

    aio_pika.connect_robust = AsyncMock(side_effect=[mock_conn_a, mock_conn_b])
    await queue._ensure_connected()
    queue._connection.is_closed = True  # type: ignore[union-attr]
    await queue._ensure_connected()
    assert aio_pika.connect_robust.await_count == 2


@pytest.mark.asyncio
async def test_response_handler_sets_result(queue: RabbitMQTaskQueue) -> None:
    import aio_pika

    mock_conn = AsyncMock()
    mock_conn.is_closed = False
    mock_ch = AsyncMock()
    mock_cq = AsyncMock()
    mock_cq.consume = AsyncMock()
    mock_ch.declare_queue = AsyncMock(return_value=mock_cq)
    mock_conn.channel = AsyncMock(return_value=mock_ch)
    aio_pika.connect_robust = AsyncMock(return_value=mock_conn)

    await queue._ensure_connected()
    handler = mock_cq.consume.call_args[0][0]

    task_id = "tid-1"
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    queue._pending[task_id] = fut

    class _Msg:
        correlation_id = task_id

        def __init__(self, body: bytes) -> None:
            self.body = body

        def process(self):
            @asynccontextmanager
            async def _cm():
                yield

            return _cm()

    await handler(_Msg(pickle.dumps({"ok": True})))
    assert fut.done()
    assert fut.result() == {"ok": True}
    assert await queue.status(task_id) == TaskStatus.DONE


@pytest.mark.asyncio
async def test_response_handler_sets_exception(queue: RabbitMQTaskQueue) -> None:
    import aio_pika

    mock_conn = AsyncMock()
    mock_conn.is_closed = False
    mock_ch = AsyncMock()
    mock_cq = AsyncMock()
    mock_cq.consume = AsyncMock()
    mock_ch.declare_queue = AsyncMock(return_value=mock_cq)
    mock_conn.channel = AsyncMock(return_value=mock_ch)
    aio_pika.connect_robust = AsyncMock(return_value=mock_conn)

    await queue._ensure_connected()
    handler = mock_cq.consume.call_args[0][0]

    task_id = "tid-err"
    fut = asyncio.get_event_loop().create_future()
    queue._pending[task_id] = fut

    class _Msg:
        correlation_id = task_id

        def __init__(self, body: bytes) -> None:
            self.body = body

        def process(self):
            @asynccontextmanager
            async def _cm():
                yield

            return _cm()

    await handler(_Msg(pickle.dumps(ValueError("boom"))))
    assert fut.done()
    with pytest.raises(ValueError, match="boom"):
        fut.result()
    assert await queue.status(task_id) == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_response_ignores_when_future_missing(queue: RabbitMQTaskQueue) -> None:
    import aio_pika

    mock_conn = AsyncMock()
    mock_conn.is_closed = False
    mock_ch = AsyncMock()
    mock_cq = AsyncMock()
    mock_cq.consume = AsyncMock()
    mock_ch.declare_queue = AsyncMock(return_value=mock_cq)
    mock_conn.channel = AsyncMock(return_value=mock_ch)
    aio_pika.connect_robust = AsyncMock(return_value=mock_conn)

    await queue._ensure_connected()
    handler = mock_cq.consume.call_args[0][0]

    class _Msg:
        correlation_id = "ghost"
        body = pickle.dumps(1)

        def process(self):
            @asynccontextmanager
            async def _cm():
                yield

            return _cm()

    await handler(_Msg())


@pytest.mark.asyncio
async def test_serve_requires_agent_name(queue: RabbitMQTaskQueue) -> None:
    agent = MagicMock()
    agent.name = ""
    with pytest.raises(ValueError, match="name"):
        await queue.serve(agent)
