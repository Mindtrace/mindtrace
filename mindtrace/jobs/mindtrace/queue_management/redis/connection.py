import time

import redis

from mindtrace.jobs.mindtrace.queue_management.base.connection_base import BrokerConnectionBase
from mindtrace.jobs.mindtrace.utils import ifnone, SingletonByArgsMeta


class RedisConnection(BrokerConnectionBase):
    """Singleton class for Redis connection.

    This class establishes and maintains a connection to the Redis server. It uses a retry loop and a PING command to
    verify connectivity.
    """

    def __init__(
        self, host: str | None = None, port: int | None = None, db: int | None = None, password: str | None = None
    ):
        """
        Initialize the Redis connection.

        Args:
            host: The Redis server host address.
            port: The Redis server port.
            db: The Redis database number.
            password: The password for the Redis server (if any).
        """
        super().__init__()
        self.host = ifnone(host, default="localhost")
        self.port = ifnone(port, default=6379)
        self.db = ifnone(db, default=0)
        self.password = password  # Use password if provided, None otherwise
        self.connection = None
        self.name = "RedisConnection"

        try:
            self.connect(max_tries=1)
        except redis.ConnectionError as e:
            self.logger.warning(f"Error connecting to Redis: {str(e)}")

    def connect(self, max_tries: int = 10):
        """Connect to the Redis server using a retry loop."""
        retries = 0
        while retries < max_tries:
            try:
                # Build connection parameters, adding password only if provided.
                conn_params = {"host": self.host, "port": self.port, "db": self.db}
                if self.password:
                    conn_params["password"] = self.password

                self.connection = redis.Redis(**conn_params)
                # Force connection by issuing a PING command.
                if self.connection.ping():
                    self.logger.debug(f"{self.name} connected to Redis at {self.host}:{self.port}, db: {self.db}.")
                    return
                else:
                    raise redis.ConnectionError("Ping failed.")

            except redis.ConnectionError:
                retries += 1
                wait_time = 2**retries
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
        """Close the connection to the Redis server."""
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception as e:
                self.logger.error(f"Error closing Redis connection: {str(e)}")
            self.connection = None
            self.logger.debug(f"{self.name} closed Redis connection.")