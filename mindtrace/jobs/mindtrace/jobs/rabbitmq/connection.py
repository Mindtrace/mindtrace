import time
from pika import PlainCredentials, ConnectionParameters, BlockingConnection, exceptions
from mindtrace.jobs.base.connection_base import BrokerConnectionBase
from mindtrace.jobs.utils.checks import ifnone

class RabbitMQConnection(BrokerConnectionBase):
    """Singleton class for RabbitMQ connection.
    The use of a singleton class ensures that only one connection is established throughout an application.
    """
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """Initialize the RabbitMQ connection.
        Args:
            host: The host address of the RabbitMQ server.
            port: The port number of the RabbitMQ server.
            username: The username for the RabbitMQ server.
            password: The password for the RabbitMQ server.
        """
        super().__init__()
        self.host = ifnone(host, default="localhost")
        self.port = ifnone(port, default=5672)
        self.username = ifnone(username, default="user")
        self.password = ifnone(password, default="password")
        self.connection = None

        
    def connect(self):
        """Connect to the RabbitMQ server."""
        retries = 0
        while retries < 10:
            try:
                credentials = PlainCredentials(self.username, self.password)
                parameters = ConnectionParameters(
                    host=self.host, port=self.port, credentials=credentials, heartbeat=0
                )
                self.connection = BlockingConnection(parameters)
                self.logger.debug(f"{self.name} connected to RabbitMQ.")
                return
            except exceptions.AMQPConnectionError:
                retries += 1
                wait_time = 0.2
                self.logger.debug(
                    f"{self.name} failed to connect to RabbitMQ, retrying in {wait_time} seconds..."
                )
                time.sleep(wait_time)
        self.logger.debug(f"{self.name} exceeded maximum number of connection retries.")
        raise exceptions.AMQPConnectionError("Failed to connect to RabbitMQ.")
    def is_connected(self):
        """Check if the connection to the RabbitMQ server is open."""
        return self.connection is not None and self.connection.is_open
    def close(self):
        """Close the connection to the RabbitMQ server."""
        if self.is_connected():
            self.connection.close()
            self.connection = None
            self.logger.debug(f"{self.name} closed RabbitMQ connection.")
    def get_channel(self):
        """Get a channel from the RabbitMQ connection."""
        if self.is_connected():
            return self.connection.channel()
        else:
            return None
