from __future__ import annotations

import asyncio
import pickle
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ._queue import AbstractTaskQueue, AgentTask, TaskStatus

if TYPE_CHECKING:
    from ..core.abstract import AbstractMindtraceAgent

try:
    import aio_pika
    import aio_pika.abc
except ImportError as e:
    raise ImportError(
        "RabbitMQTaskQueue requires aio-pika. Install it with: pip install 'mindtrace-agents[distributed-rabbitmq]'"
    ) from e


class RabbitMQTaskQueue(AbstractTaskQueue):
    """Task queue backed by RabbitMQ using the AMQP RPC pattern.

    Caller side:  submit() publishes to the agent's named queue and waits on a reply queue.
    Worker side:  serve() consumes from the agent's named queue and publishes results back.

    Note: AgentTask.deps must be pickle-serializable. For production, avoid passing
    live connections in deps across processes — use clients that reconnect on the worker side.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self._pending: dict[str, asyncio.Future] = {}
        self._statuses: dict[str, TaskStatus] = {}
        self._connection: aio_pika.abc.AbstractConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._callback_queue: aio_pika.abc.AbstractQueue | None = None

    async def _ensure_connected(self) -> tuple[aio_pika.abc.AbstractChannel, aio_pika.abc.AbstractQueue]:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self.url)
            self._channel = await self._connection.channel()
            self._callback_queue = await self._channel.declare_queue(exclusive=True, auto_delete=True)

            async def _on_response(message: aio_pika.abc.AbstractIncomingMessage) -> None:
                async with message.process():
                    correlation_id = message.correlation_id
                    future = self._pending.get(correlation_id)
                    if future and not future.done():
                        result = pickle.loads(message.body)
                        if isinstance(result, Exception):
                            self._statuses[correlation_id] = TaskStatus.FAILED
                            future.set_exception(result)
                        else:
                            self._statuses[correlation_id] = TaskStatus.DONE
                            future.set_result(result)

            await self._callback_queue.consume(_on_response)

        return self._channel, self._callback_queue  # type: ignore[return-value]

    async def submit(self, task: AgentTask) -> str:
        channel, callback_queue = await self._ensure_connected()
        task_id = str(uuid4())

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[task_id] = future
        self._statuses[task_id] = TaskStatus.PENDING

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=pickle.dumps(task),
                correlation_id=task_id,
                reply_to=callback_queue.name,
            ),
            routing_key=task.agent_name,
        )
        self._statuses[task_id] = TaskStatus.RUNNING
        return task_id

    async def get_result(self, task_id: str) -> Any:
        future = self._pending.get(task_id)
        if future is None:
            raise KeyError(f"Unknown task_id: {task_id!r}")
        return await future

    async def cancel(self, task_id: str) -> None:
        future = self._pending.get(task_id)
        if future and not future.done():
            future.cancel()
            self._statuses[task_id] = TaskStatus.FAILED

    async def status(self, task_id: str) -> TaskStatus:
        return self._statuses.get(task_id, TaskStatus.PENDING)

    async def serve(self, agent: AbstractMindtraceAgent) -> None:
        """Worker side — consume tasks for this agent and publish results back.

        Blocks until the process is interrupted.
        """
        agent_name = agent.name
        if not agent_name:
            raise ValueError("Agent must have a name to serve via RabbitMQTaskQueue.")

        connection = await aio_pika.connect_robust(self.url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(agent_name, durable=True)

            async def _on_task(message: aio_pika.abc.AbstractIncomingMessage) -> None:
                async with message.process():
                    task: AgentTask = pickle.loads(message.body)
                    try:
                        result = await agent.run(task.input, deps=task.deps, session_id=task.session_id)
                        body = pickle.dumps(result)
                    except Exception as exc:
                        body = pickle.dumps(exc)

                    if message.reply_to:
                        await channel.default_exchange.publish(
                            aio_pika.Message(
                                body=body,
                                correlation_id=message.correlation_id,
                            ),
                            routing_key=message.reply_to,
                        )

            await queue.consume(_on_task)
            await asyncio.Future()  # run until interrupted


__all__ = ["RabbitMQTaskQueue"]
