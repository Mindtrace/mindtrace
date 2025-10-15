import json
import threading
import time

import redis

from mindtrace.core import ifnone
from mindtrace.jobs.base.connection_base import BrokerConnectionBase
from mindtrace.jobs.redis.fifo_queue import RedisQueue
from mindtrace.jobs.redis.priority import RedisPriorityQueue
from mindtrace.jobs.redis.stack import RedisStack


class RedisConnection(BrokerConnectionBase):
    METADATA_KEY = "mindtrace:queue_metadata"  # Centralized metadata key
    EVENTS_CHANNEL = "mindtrace:queue_events"  # Pub/Sub channel for queue events
    """Singleton class for Redis connection.
    This class establishes and maintains a connection to the Redis server. It uses a retry loop and a PING command to
    verify connectivity.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int | None = None,
        password: str | None = None,
        socket_timeout: float | None = None,
        socket_connect_timeout: float | None = None,
    ):
        """
        Initialize the Redis connection.
        Args:
            host: The Redis server host address.
            port: The Redis server port.
            db: The Redis database number.
            password: The password for the Redis server (if any).
            socket_timeout: Timeout for socket operations (in seconds).
            socket_connect_timeout: Timeout for socket connect (in seconds).
        """
        super().__init__()
        self.host = ifnone(host, default="localhost")
        self.port = ifnone(port, default=6379)
        self.db = ifnone(db, default=0)
        self.password = password  # Use password if provided, None otherwise
        self.socket_timeout = ifnone(socket_timeout, default=5.0)
        self.socket_connect_timeout = ifnone(socket_connect_timeout, default=2.0)
        self.connection: redis.Redis = None  # type: ignore
        try:
            self.connect(max_tries=1)
        except redis.ConnectionError as e:
            self.logger.warning(f"Error connecting to Redis: {str(e)}")
        self.queues = {}
        self._local_lock = threading.Lock()  # Thread lock for local state modifications
        self._shutdown_event = threading.Event()  # Event to signal shutdown to background thread
        self._pubsub = None  # Store pubsub instance for proper cleanup
        self._event_thread = None  # Store thread reference for cleanup
        self._load_queue_metadata()  # Load previously declared queues from metadata.
        self._start_event_listener()  # Start a background thread to listen for queue events.

    def connect(self, max_tries: int = 10):
        """Connect to the Redis server using a retry loop."""
        retries = 0
        while retries < max_tries:
            try:
                conn_params = {
                    "host": self.host,
                    "port": self.port,
                    "db": self.db,
                    "socket_timeout": self.socket_timeout,
                    "socket_connect_timeout": self.socket_connect_timeout,
                }
                if self.password:
                    conn_params["password"] = self.password
                self.connection = redis.Redis(**conn_params)
                if self.connection.ping():
                    self.logger.debug(f"{self.name} connected to Redis at {self.host}:{self.port}, db: {self.db}.")
                    return
                else:
                    raise redis.ConnectionError("Ping failed.")
            except redis.ConnectionError:
                retries += 1
                wait_time = min(2**retries, 30)  # Cap wait time at 30 seconds
                self.logger.debug(f"{self.name} failed to connect to Redis, retrying in {wait_time} seconds...")
                if retries < max_tries:
                    time.sleep(wait_time)
        self.logger.debug(f"{self.name} exceeded maximum number of connection retries to Redis.")
        raise redis.ConnectionError("Failed to connect to Redis.")

    def is_connected(self) -> bool:
        """Return True if the connection to Redis is active (verified via PING)."""
        try:
            return self.connection is not None and self.connection.ping()
        except redis.ConnectionError:
            return False

    def close(self):
        """Close the connection to the Redis server and shutdown background thread."""
        # Signal the background thread to shutdown
        self._shutdown_event.set()

        # Close pubsub connection if it exists
        with self._local_lock:
            if self._pubsub is not None:
                try:
                    self._pubsub.close()
                except Exception as e:
                    self.logger.error(f"Error closing pubsub connection: {str(e)}")
                self._pubsub = None

        # Wait for the background thread to finish (with timeout)
        if self._event_thread is not None and self._event_thread.is_alive():
            self._event_thread.join(timeout=1.0)
            if self._event_thread.is_alive():
                self.logger.warning("Background event thread did not shutdown gracefully")

        # Close main Redis connection
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception as e:
                self.logger.error(f"Error closing Redis connection: {str(e)}")
            self.connection = None  # type: ignore
            self.logger.debug(f"{self.name} closed Redis connection.")

    def __del__(self):
        """Ensure cleanup happens when the object is garbage collected."""
        try:
            self.close()
        except Exception:
            pass

    def _start_event_listener(self):
        """Start a background thread to subscribe to queue events and update local state."""
        self._event_thread = threading.Thread(target=self._subscribe_to_events, daemon=True)
        self._event_thread.start()

    def _subscribe_to_events(self):
        try:
            self._pubsub = self.connection.pubsub()
            self._pubsub.subscribe(self.EVENTS_CHANNEL)

            for message in self._pubsub.listen():
                if self._shutdown_event.is_set():
                    break
                if message["type"] != "message":
                    continue

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
                                    host=self.host,
                                    port=self.port,
                                    db=self.db,
                                )
                            elif qtype.lower() == "stack":
                                instance = RedisStack(
                                    qname,
                                    host=self.host,
                                    port=self.port,
                                    db=self.db,
                                )
                            elif qtype.lower() == "priority":
                                instance = RedisPriorityQueue(
                                    qname,
                                    host=self.host,
                                    port=self.port,
                                    db=self.db,
                                )
                            else:
                                continue
                            self.queues[qname] = instance
                        elif event == "delete":
                            if qname in self.queues:
                                del self.queues[qname]
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Event listener thread exception: {str(e)}")
        finally:
            with self._local_lock:
                if self._pubsub is not None:
                    try:
                        self._pubsub.close()
                    except Exception:
                        pass
                    self._pubsub = None

    def _load_queue_metadata(self):
        """Load all declared queues from the centralized metadata hash."""
        metadata = self.connection.hgetall(self.METADATA_KEY)
        for queue, queue_type in metadata.items():
            qname = queue.decode("utf-8") if isinstance(queue, bytes) else queue
            qtype = queue_type.decode("utf-8") if isinstance(queue_type, bytes) else queue_type
            with self._local_lock:
                if qtype.lower() == "fifo":
                    instance = RedisQueue(
                        qname,
                        host=self.host,
                        port=self.port,
                        db=self.db,
                    )
                elif qtype.lower() == "stack":
                    instance = RedisStack(
                        qname,
                        host=self.host,
                        port=self.port,
                        db=self.db,
                    )
                elif qtype.lower() == "priority":
                    instance = RedisPriorityQueue(
                        qname,
                        host=self.host,
                        port=self.port,
                        db=self.db,
                    )
                else:
                    continue
                self.queues[qname] = instance

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
