import json
import uuid

import pydantic

from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.consumers.consumer import Consumer
from mindtrace.jobs.redis.connection import RedisConnection
from mindtrace.jobs.redis.consumer_backend import RedisConsumerBackend
from mindtrace.jobs.redis.fifo_queue import RedisQueue
from mindtrace.jobs.redis.priority import RedisPriorityQueue
from mindtrace.jobs.redis.stack import RedisStack


class RedisClient(OrchestratorBackend):
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        """Initialize the Redis client and connect to the Redis server.
        Args:
            host: Redis server hostname.
            port: Redis server port.
            db: Redis database number.
        """
        super().__init__()
        self.redis_params = {"host": host, "port": port, "db": db}
        self.connection = RedisConnection(**self.redis_params)

    @property
    def consumer_backend_args(self):
        return {"cls": "mindtrace.jobs.redis.consumer_backend.RedisConsumerBackend", "kwargs": self.redis_params}

    def create_consumer_backend(self, consumer_frontend: Consumer, queue_name: str) -> RedisConsumerBackend:
        return RedisConsumerBackend(queue_name, consumer_frontend, **self.consumer_backend_args["kwargs"])

    def declare_queue(self, queue_name: str, queue_type: str = "fifo", **kwargs) -> dict[str, str]:
        """Declare a Redis-backed queue of type 'fifo', 'stack', or 'priority'."""
        with self.connection._local_lock:
            if queue_name in self.connection.queues:
                return {
                    "status": "success",
                    "message": f"Queue '{queue_name}' already exists.",
                }
        lock = self.connection.connection.lock("mindtrace:queue_lock", timeout=5)
        if not lock.acquire(blocking=True):
            raise BlockingIOError("Could not acquire distributed lock.")
        try:
            pipe = self.connection.connection.pipeline()
            pipe.hset(self.connection.METADATA_KEY, queue_name, queue_type.lower())
            pipe.execute()
            if queue_type.lower() == "fifo":
                instance = RedisQueue(
                    queue_name,
                    host=self.redis_params["host"],
                    port=self.redis_params["port"],
                    db=self.redis_params["db"],
                )
            elif queue_type.lower() == "stack":
                instance = RedisStack(
                    queue_name,
                    host=self.redis_params["host"],
                    port=self.redis_params["port"],
                    db=self.redis_params["db"],
                )
            elif queue_type.lower() == "priority":
                instance = RedisPriorityQueue(
                    queue_name,
                    host=self.redis_params["host"],
                    port=self.redis_params["port"],
                    db=self.redis_params["db"],
                )
            else:
                raise TypeError(f"Unknown queue type '{queue_type}'.")
            with self.connection._local_lock:
                self.connection.queues[queue_name] = instance
            event_data = json.dumps({"event": "declare", "queue": queue_name, "queue_type": queue_type})
            self.connection.connection.publish(self.connection.EVENTS_CHANNEL, event_data)
            return {
                "status": "success",
                "message": f"Queue '{queue_name}' declared as {queue_type} successfully.",
            }
        finally:
            lock.release()

    def delete_queue(self, queue_name: str, **kwargs) -> dict:
        """Delete a declared queue.
        Uses distributed locking and transactions to remove the queue from the centralized metadata, and publishes an
        event to notify other clients.
        """
        with self.connection._local_lock:
            if queue_name not in self.connection.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
        lock = self.connection.connection.lock("mindtrace:queue_lock", timeout=5)
        if not lock.acquire(blocking=True):
            raise BlockingIOError("Could not acquire distributed lock.")
        try:
            pipe = self.connection.connection.pipeline()
            pipe.hdel(self.connection.METADATA_KEY, queue_name)
            pipe.execute()
            with self.connection._local_lock:
                if queue_name in self.connection.queues:
                    del self.connection.queues[queue_name]
            event_data = json.dumps({"event": "delete", "queue": queue_name})
            self.connection.connection.publish(self.connection.EVENTS_CHANNEL, event_data)
            return {
                "status": "success",
                "message": f"Queue '{queue_name}' deleted successfully.",
            }
        finally:
            lock.release()

    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs) -> str:
        """Publish a message (a pydantic model) to the specified Redis queue."""
        priority = kwargs.get("priority")
        with self.connection._local_lock:
            if queue_name not in self.connection.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
            instance = self.connection.queues[queue_name]
        try:
            message_dict = message.model_dump()
            if "job_id" not in message_dict:
                message_dict["job_id"] = str(uuid.uuid1())
            body = json.dumps(message_dict)
            if type(instance).__name__ == "RedisPriorityQueue" and priority is not None:
                instance.push(item=body, priority=priority)
            else:
                instance.push(item=body)
            return message_dict["job_id"]
        except Exception:
            raise

    def clean_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Clean (purge) a specified Redis queue by deleting its underlying key.

        Args:
            queue_name: The name of the declared queue to be cleaned.

        Raises:
            KeyError if the queue is not declared.
        """
        with self.connection._local_lock:
            if queue_name not in self.connection.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
            instance = self.connection.queues[queue_name]
        lock = self.connection.connection.lock("mindtrace:queue_lock", timeout=5)
        if not lock.acquire(blocking=True):
            raise BlockingIOError("Could not acquire distributed lock.")
        try:
            count = self.connection.connection.llen(instance.key)
            self.connection.connection.delete(instance.key)
            return {
                "status": "success",
                "message": f"Queue '{queue_name}' cleaned; deleted {count} key(s).",
            }
        except Exception:
            raise
        finally:
            lock.release()

    def move_to_dlq(
        self,
        source_queue: str,
        dlq_name: str,
        message: pydantic.BaseModel,
        error_details: str,
        **kwargs,
    ):
        """Move a failed message to a dead letter queue"""
        pass

    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        return self.connection.count_queue_messages(queue_name, **kwargs)

    def close(self):
        """Close the Redis connection and clean up resources."""
        if hasattr(self, "connection") and self.connection is not None:
            self.connection.close()
            self.connection = None

    def __del__(self):
        """Ensure cleanup happens when the object is garbage collected."""
        try:
            self.close()
        except Exception:
            pass
