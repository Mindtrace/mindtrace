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
        "RabbitMQ queues require aio-pika. Install it with: pip install 'mindtrace-agents[distributed-rabbitmq]'"
    ) from e


_LEGACY_MIGRATION_MSG = (
    "RabbitMQTaskQueue has been replaced by RabbitMQAgentTaskQueue "
    "(mindtrace-agents[distributed-rabbitmq]). "
    "The legacy pickle-based queue is a security risk and will be removed in a future release. "
    "See the distributed-agents migration guide for the new envelope-based API."
)


class _LegacyPickleRabbitMQTaskQueue(AbstractTaskQueue):
    """DEPRECATED. Use RabbitMQAgentTaskQueue instead.

    This class is retained only to allow graceful migration. It serialises
    AgentTask.deps with pickle, which is unsafe across trust boundaries.
    Do NOT use in new code.
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
                        result = pickle.loads(message.body)  # noqa: S301
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
                body=pickle.dumps(task),  # noqa: S301
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
        """Worker side — consume tasks for this agent and publish results back."""
        agent_name = agent.name
        if not agent_name:
            raise ValueError("Agent must have a name to serve via queue.")

        connection = await aio_pika.connect_robust(self.url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(agent_name, durable=True)

            async def _on_task(message: aio_pika.abc.AbstractIncomingMessage) -> None:
                async with message.process():
                    task: AgentTask = pickle.loads(message.body)  # noqa: S301
                    try:
                        result = await agent.run(task.input, deps=task.deps, session_id=task.session_id)
                        body = pickle.dumps(result)  # noqa: S301
                    except Exception as exc:
                        body = pickle.dumps(exc)  # noqa: S301

                    if message.reply_to:
                        await channel.default_exchange.publish(
                            aio_pika.Message(
                                body=body,
                                correlation_id=message.correlation_id,
                            ),
                            routing_key=message.reply_to,
                        )

            await queue.consume(_on_task)
            await asyncio.Future()


def __getattr__(name: str) -> object:
    if name == "RabbitMQTaskQueue":
        raise ImportError(_LEGACY_MIGRATION_MSG)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class RabbitMQAgentTaskQueue(AbstractTaskQueue):
    """Envelope-based RabbitMQ task queue.

    Publishes AgentTaskEnvelope JSON messages to a durable RabbitMQ queue.
    Results and cancellation flags are stored in Redis. Failed tasks are
    routed to a dead-letter queue after max_retries exhausted.
    """

    def __init__(
        self,
        rabbitmq_url: str,
        redis_url: str,
        queue_name: str = "mindtrace.agent.tasks",
        dlq_name: str = "mindtrace.agent.tasks.dlq",
        result_ttl: int = 3600,
        max_retries: int = 3,
    ) -> None:
        try:
            import redis.asyncio as _aioredis  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "RabbitMQAgentTaskQueue requires redis. "
                "Install it with: pip install 'mindtrace-agents[distributed-rabbitmq]'"
            ) from e
        self._rabbitmq_url = rabbitmq_url
        self._redis_url = redis_url
        self._queue_name = queue_name
        self._dlq_name = dlq_name
        self._result_ttl = result_ttl
        self._max_retries = max_retries
        self._redis_client: Any = None
        self._amqp_connection: Any = None
        self._amqp_channel: Any = None

    async def _get_redis(self) -> Any:
        if self._redis_client is None:
            import redis.asyncio as aioredis
            self._redis_client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis_client

    async def _get_channel(self) -> Any:
        if self._amqp_connection is None or self._amqp_connection.is_closed:
            self._amqp_connection = await aio_pika.connect_robust(self._rabbitmq_url)
            self._amqp_channel = await self._amqp_connection.channel()
            await self._amqp_channel.declare_queue(self._queue_name, durable=True)
            await self._amqp_channel.declare_queue(self._dlq_name, durable=True)
        return self._amqp_channel

    async def submit(self, task: AgentTask) -> str:
        """Wrap task in an AgentTaskEnvelope and publish to RabbitMQ.

        If the gateway already built a full envelope (stored in task.metadata["envelope"]),
        use it directly so that run_context fields (user_id, project_id, org_id, etc.)
        are preserved. Otherwise, construct a minimal envelope from the task fields.
        """
        from ..context.propagation import AgentRunContext, AgentTaskEnvelope, TaskProvenance
        from uuid import uuid4 as _uuid4

        pre_built = (task.metadata or {}).get("envelope")
        if pre_built:
            envelope = AgentTaskEnvelope.model_validate_json(pre_built)
        else:
            trace_id = _uuid4().hex + _uuid4().hex
            span_id = _uuid4().hex[:16]
            session_id = task.session_id or str(_uuid4())
            run_context = AgentRunContext(
                trace_id=trace_id,
                span_id=span_id,
                session_id=session_id,
                user_id=task.user_id or "",
            )
            provenance = TaskProvenance(
                submitter_id="",
                submitter_role="service",
                origin_gateway_id="",
            )
            envelope = AgentTaskEnvelope(
                agent_name=task.agent_name,
                input=task.input,
                session_id=task.session_id,
                run_context=run_context,
                provenance=provenance,
            )
        task_id = envelope.task_id

        channel = await self._get_channel()
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=envelope.model_dump_json().encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=self._queue_name,
        )

        redis = await self._get_redis()
        await redis.set(f"status:{task_id}", TaskStatus.PENDING.value, ex=self._result_ttl)
        return task_id

    async def get_result(self, task_id: str, timeout: int = 300) -> Any:
        """Poll Redis result key with exponential backoff."""
        import asyncio as _asyncio
        import json as _json

        redis = await self._get_redis()
        delay = 0.5
        elapsed = 0.0
        while elapsed < timeout:
            raw = await redis.get(f"result:{task_id}")
            if raw is not None:
                data = _json.loads(raw)
                if data.get("status") == "error":
                    raise RuntimeError(data.get("message", "Task failed"))
                return data.get("result")
            await _asyncio.sleep(delay)
            elapsed += delay
            delay = min(delay * 2, 10.0)
        raise TimeoutError(f"Task {task_id!r} result not available within {timeout}s")

    async def dequeue(self) -> str | None:
        """Pull one message from the queue without a persistent consumer.

        Returns the raw JSON string of the envelope, or None if the queue is
        empty. The message is acked immediately on successful retrieval.
        """
        channel = await self._get_channel()
        queue = await channel.declare_queue(self._queue_name, durable=True, passive=True)
        msg = await queue.get(no_ack=False, fail=False)
        if msg is None:
            return None
        await msg.ack()
        return msg.body.decode()

    async def cancel(self, task_id: str) -> None:
        redis = await self._get_redis()
        await redis.set(f"cancel:{task_id}", "1", ex=self._result_ttl)
        await redis.set(f"status:{task_id}", TaskStatus.FAILED.value, ex=self._result_ttl)

    async def status(self, task_id: str) -> TaskStatus:
        redis = await self._get_redis()
        raw = await redis.get(f"status:{task_id}")
        if raw is None:
            return TaskStatus.PENDING
        return TaskStatus(raw)

    async def list_dlq(self, limit: int = 100) -> list[dict]:
        """Return up to `limit` messages from the DLQ without consuming them."""
        import json as _json

        connection = await aio_pika.connect_robust(self._rabbitmq_url)
        results: list[dict] = []
        try:
            channel = await connection.channel()
            queue = await channel.declare_queue(self._dlq_name, durable=True, passive=True)
            collected: list[aio_pika.abc.AbstractIncomingMessage] = []
            for _ in range(limit):
                msg = await queue.get(no_ack=False, fail=False)
                if msg is None:
                    break
                collected.append(msg)
                try:
                    results.append(_json.loads(msg.body))
                except Exception:
                    results.append({"raw": msg.body.decode(errors="replace")})
            for msg in collected:
                await msg.nack(requeue=True)
        finally:
            await connection.close()
        return results

    async def requeue_from_dlq(self, task_id: str) -> bool:
        """Move a specific task_id message from DLQ back to the main queue.

        Peeks messages one at a time; acks and republishes only the matching
        task_id, nack-requeues everything else. Returns True if found.
        """
        import json as _json

        connection = await aio_pika.connect_robust(self._rabbitmq_url)
        found = False
        try:
            channel = await connection.channel()
            queue = await channel.declare_queue(self._dlq_name, durable=True, passive=True)
            queue_length = queue.declaration_result.message_count
            skipped: list[aio_pika.abc.AbstractIncomingMessage] = []
            for _ in range(queue_length):
                msg = await queue.get(no_ack=False, fail=False)
                if msg is None:
                    break
                try:
                    body = _json.loads(msg.body)
                except Exception:
                    body = {}
                if body.get("task_id") == task_id:
                    body["retry_count"] = 0
                    await channel.default_exchange.publish(
                        aio_pika.Message(
                            body=_json.dumps(body).encode(),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        ),
                        routing_key=self._queue_name,
                    )
                    await msg.ack()
                    found = True
                    break
                else:
                    skipped.append(msg)
            for msg in skipped:
                await msg.nack(requeue=True)
        finally:
            await connection.close()
        return found

    async def purge_dlq(self) -> int:
        """Purge all messages from the DLQ. Returns count purged."""
        connection = await aio_pika.connect_robust(self._rabbitmq_url)
        try:
            channel = await connection.channel()
            queue = await channel.declare_queue(self._dlq_name, durable=True, passive=True)
            count_before = queue.declaration_result.message_count
            await queue.purge()
        finally:
            await connection.close()
        return count_before

    async def close(self) -> None:
        if self._redis_client is not None:
            await self._redis_client.aclose()
        if self._amqp_connection is not None and not self._amqp_connection.is_closed:
            await self._amqp_connection.close()


__all__ = ["_LegacyPickleRabbitMQTaskQueue", "RabbitMQAgentTaskQueue"]
