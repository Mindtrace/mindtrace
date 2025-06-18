import json
import threading
import uuid
from queue import Empty
from typing import Any, Dict, List, Optional

import pydantic
import redis

from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.redis.fifo_queue import RedisQueue
from mindtrace.jobs.redis.priority import RedisPriorityQueue
from mindtrace.jobs.redis.stack import RedisStack


class RedisClient(OrchestratorBackend):
    METADATA_KEY = "mtrix:queue_metadata"  # Centralized metadata key
    EVENTS_CHANNEL = "mtrix:queue_events"  # Pub/Sub channel for queue events
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        """Initialize the Redis client and connect to the Redis server.
        Args:
            host: Redis server hostname.
            port: Redis server port.
            db: Redis database number.
        """
        super().__init__()
        self.redis_params = {"host": host, "port": port, "db": db}
        self.redis = redis.Redis(**self.redis_params)
        self.queues: dict[str, any] = {}  # Local cache of queue objects
        self._local_lock = threading.Lock()  # Thread lock for local state modifications
        self._load_queue_metadata()  # Load previously declared queues from metadata.
        self._start_event_listener() # Start a background thread to listen for queue events.
    
    def _load_queue_metadata(self):
        """Load all declared queues from the centralized metadata hash."""
        metadata = self.redis.hgetall(self.METADATA_KEY)
        for queue, queue_type in metadata.items():
            qname = queue.decode("utf-8") if isinstance(queue, bytes) else queue
            qtype = (
                queue_type.decode("utf-8")
                if isinstance(queue_type, bytes)
                else queue_type
            )
            with self._local_lock:
                if qtype.lower() == "fifo":
                    instance = RedisQueue(
                        qname,
                        host=self.redis_params["host"],
                        port=self.redis_params["port"],
                        db=self.redis_params["db"],
                    )
                elif qtype.lower() == "stack":
                    instance = RedisStack(
                        qname,
                        host=self.redis_params["host"],
                        port=self.redis_params["port"],
                        db=self.redis_params["db"],
                    )
                elif qtype.lower() == "priority":
                    instance = RedisPriorityQueue(
                        qname,
                        host=self.redis_params["host"],
                        port=self.redis_params["port"],
                        db=self.redis_params["db"],
                    )
                else:
                    continue
                self.queues[qname] = instance

    def _start_event_listener(self):
        """Start a background thread to subscribe to queue events and update local state."""
        thread = threading.Thread(target=self._subscribe_to_events, daemon=True)
        thread.start()

    def _subscribe_to_events(self):
        pubsub = self.redis.pubsub()
        pubsub.subscribe(self.EVENTS_CHANNEL)
        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"].decode("utf-8"))
                    event = data.get("event")
                    qname = data.get("queue")
                    qtype = data.get("queue_type")
                    with self._local_lock:
                        if event == "declare":
                            if qtype.lower() == "fifo":
                                instance = RedisQueue(
                                    qname,
                                    host=self.redis_params["host"],
                                    port=self.redis_params["port"],
                                    db=self.redis_params["db"],
                                )
                            elif qtype.lower() == "stack":
                                instance = RedisStack(
                                    qname,
                                    host=self.redis_params["host"],
                                    port=self.redis_params["port"],
                                    db=self.redis_params["db"],
                                )
                            elif qtype.lower() == "priority":
                                instance = RedisPriorityQueue(
                                    qname,
                                    host=self.redis_params["host"],
                                    port=self.redis_params["port"],
                                    db=self.redis_params["db"],
                                )
                            else:
                                continue
                            self.queues[qname] = instance
                        elif event == "delete":
                            if qname in self.queues:
                                del self.queues[qname]
                except Exception:
                    pass

    def declare_queue(self, queue_name: str, **kwargs) -> dict:
        """Declare a Redis-backed queue of type 'fifo', 'stack', or 'priority'."""
        queue_type = kwargs.get("queue_type", "fifo")
        force = kwargs.get("force", False)
        with self._local_lock:
            if queue_name in self.queues:
                return {
                    "status": "success",
                    "message": f"Queue '{queue_name}' already exists.",
                }
        lock = self.redis.lock("mtrix:queue_lock", timeout=5)
        if not lock.acquire(blocking=True):
            raise BlockingIOError("Could not acquire distributed lock.")
        try:
            pipe = self.redis.pipeline()
            pipe.hset(self.METADATA_KEY, queue_name, queue_type.lower())
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
            with self._local_lock:
                self.queues[queue_name] = instance
            event_data = json.dumps(
                {"event": "declare", "queue": queue_name, "queue_type": queue_type}
            )
            self.redis.publish(self.EVENTS_CHANNEL, event_data)
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
        with self._local_lock:
            if queue_name not in self.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
        lock = self.redis.lock("mtrix:queue_lock", timeout=5)
        if not lock.acquire(blocking=True):
            raise BlockingIOError("Could not acquire distributed lock.")
        try:
            pipe = self.redis.pipeline()
            pipe.hdel(self.METADATA_KEY, queue_name)
            pipe.execute()
            with self._local_lock:
                if queue_name in self.queues:
                    del self.queues[queue_name]
            event_data = json.dumps({"event": "delete", "queue": queue_name})
            self.redis.publish(self.EVENTS_CHANNEL, event_data)
            return {
                "status": "success",
                "message": f"Queue '{queue_name}' deleted successfully.",
            }
        finally:
            lock.release()

    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs) -> str:
        """Publish a message (a pydantic model) to the specified Redis queue."""
        priority = kwargs.get("priority")
        with self._local_lock:
            if queue_name not in self.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
            instance = self.queues[queue_name]
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

    def receive_message(self, queue_name: str, **kwargs) -> Optional[dict]:
        """Retrieve a message from a specified Redis queue.

        Returns the message as a dict.
        """
        with self._local_lock:
            if queue_name not in self.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
            instance = self.queues[queue_name]
        try:
            if hasattr(instance, "get"):
                raw_message = instance.get(block=False, timeout=None)
            elif hasattr(instance, "pop"):
                raw_message = instance.pop(block=False, timeout=None)
            else:
                raise Exception("Queue type does not support receiving messages.")
            message_dict = json.loads(raw_message)
            return message_dict
        except Empty:
            return None
        except Exception:
            return None

    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        """Count the number of messages in a specified Redis queue.

        Args:
            queue_name: The name of the declared queue.

        Returns:
            Number of messages in the given queue.

        Raises:
            KeyError if the queue is not declared.
        """
        with self._local_lock:
            if queue_name not in self.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
            instance = self.queues[queue_name]
        return instance.qsize()

    def clean_queue(self, queue_name: str, **kwargs) -> dict:
        """Clean (purge) a specified Redis queue by deleting its underlying key.

        Args:
            queue_name: The name of the declared queue to be cleaned.

        Raises:
            KeyError if the queue is not declared.
        """
        with self._local_lock:
            if queue_name not in self.queues:
                error_msg = f"Queue '{queue_name}' is not declared."
                raise KeyError(error_msg)
            instance = self.queues[queue_name]
        lock = self.redis.lock("mtrix:queue_lock", timeout=5)
        if not lock.acquire(blocking=True):
            raise BlockingIOError("Could not acquire distributed lock.")
        try:
            count = self.redis.llen(instance.key)
            self.redis.delete(instance.key)
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
