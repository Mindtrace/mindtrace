import json
import uuid

import pika
import pika.exceptions
import pydantic
from pika import BasicProperties, DeliveryMode

from mindtrace.core import ifnone
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.consumers.consumer import Consumer
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend


class RabbitMQClient(OrchestratorBackend):
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """Initialize the RabbitMQ client with connection parameters.
        Args:
            host: RabbitMQ server hostname.
            port: RabbitMQ server port.
            username: Username for RabbitMQ authentication.
            password: Password for RabbitMQ authentication.
        """
        super().__init__()
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._connection = None
        self._channel = None

    @property
    def connection(self):
        if self._connection is None:
            self._connection = RabbitMQConnection(
                host=self._host, port=self._port, username=self._username, password=self._password
            )
            self._connection.connect()
        return self._connection

    @property
    def channel(self):
        if self._channel is None:
            self._channel = self.connection.get_channel()
            try:
                self._channel.exchange_declare(exchange="default", passive=True)
            except pika.exceptions.ChannelClosedByBroker:
                self._channel = self.connection.get_channel()
                self._channel.exchange_declare(
                    exchange="default", exchange_type="direct", durable=True, auto_delete=False
                )
        return self._channel

    @channel.setter
    def channel(self, value):
        self._channel = value

    def create_connection(self):
        connection = RabbitMQConnection(
            host=self._host, port=self._port, username=self._username, password=self._password
        )
        connection.connect()
        return connection.get_channel()

    @property
    def consumer_backend_args(self):
        return {
            "cls": "mindtrace.jobs.rabbitmq.consumer_backend.RabbitMQConsumerBackend",
            "kwargs": {
                "host": self._host,
                "port": self._port,
                "username": self._username,
                "password": self._password,
            },
        }

    def create_consumer_backend(self, consumer_frontend: Consumer, queue_name: str) -> RabbitMQConsumerBackend:
        return RabbitMQConsumerBackend(queue_name, consumer_frontend, **self.consumer_backend_args["kwargs"])

    def declare_exchange(
        self,
        *,
        exchange: str,
        exchange_type: str = "direct",
        durable: bool = True,
        auto_delete: bool = False,
        **kwargs,
    ):
        """Declare a RabbitMQ exchange.
        Args:
            exchange: Name of the exchange to declare.
            exchange_type: Type of the exchange (e.g., 'direct', 'topic', 'fanout').
            durable: Make the exchange durable.
            auto_delete: Automatically delete the exchange when no queues are bound.
        """
        try:
            self.channel.exchange_declare(exchange=exchange, passive=True)
            self.logger.debug(f"Exchange '{exchange}' already exists. Not declaring it again.")
            return {
                "status": "success",
                "message": f"Exchange '{exchange}' already exists. Not declaring it again.",
            }
        except pika.exceptions.ChannelClosedByBroker:
            try:
                self.channel = self.connection.get_channel()  # Re-establish channel after it was closed
                self.channel.exchange_declare(
                    exchange=exchange,
                    exchange_type=exchange_type,
                    durable=durable,
                    auto_delete=auto_delete,
                )
                self.logger.debug(f"Exchange '{exchange}' declared successfully.")
                return {
                    "status": "success",
                    "message": f"Exchange '{exchange}' declared successfully.",
                }
            except Exception as e:
                raise RuntimeError(f"Could not declare exchange '{exchange}': {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Could not declare exchange '{exchange}': {str(e)}")

    def declare_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Declare a RabbitMQ queue.
        Args:
            queue: Name of the queue to declare.
            exchange: Name of the exchange to bind the queue to.
            durable: Make the queue durable.
            exclusive: Make the queue exclusive to the connection.
            auto_delete: Automatically delete the queue when no consumers are connected.
            routing_key: Routing key for binding the queue to the exchange.
            force: Force exchange creation if it doesn't exist.
            max_priority: Maximum priority for priority queue (0-255).
        """
        if "queue_type" in kwargs:
            self.logger.warning("queue_type is not available for RabbitMQClient. Creating a FIFO queue.")
        queue = queue_name
        exchange = kwargs.get("exchange")
        durable = kwargs.get("durable", True)
        exclusive = kwargs.get("exclusive", False)
        auto_delete = kwargs.get("auto_delete", False)
        routing_key = kwargs.get("routing_key")
        force = kwargs.get("force", False)
        max_priority = kwargs.get("max_priority")
        queue_arguments = {}
        if max_priority is not None:
            queue_arguments["x-max-priority"] = max_priority
        try:
            self.channel.queue_declare(queue=queue, passive=True)
            return {"status": "success", "message": f"Queue '{queue}' already exists."}
        except pika.exceptions.ChannelClosedByBroker:
            self.channel = self.connection.get_channel()
            try:
                if exchange:
                    self.logger.info(f"Using provided exchange: {exchange}.")
                else:
                    exchange = "default"
                    self.logger.info(f"Exchange not provided. Using default exchange: {exchange}.")
                try:
                    self.channel.exchange_declare(exchange=exchange, passive=True)
                    self.logger.debug(f"Exchange '{exchange}' exists. Binding queue '{queue}' to it.")
                    self.channel.queue_declare(
                        queue=queue,
                        durable=durable,
                        exclusive=exclusive,
                        auto_delete=auto_delete,
                        arguments=queue_arguments,
                    )
                    self.logger.debug(f"Queue '{queue}' declared successfully.")
                    self.channel.queue_bind(
                        queue=queue,
                        exchange=exchange,
                        routing_key=ifnone(routing_key, default=queue),
                    )
                    return {
                        "status": "success",
                        "message": f"Queue '{queue}' declared and bound to exchange '{exchange}' successfully.",
                    }
                except pika.exceptions.ChannelClosedByBroker:
                    self.channel = self.connection.get_channel()
                    if force:
                        self.channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
                        self.logger.debug(f"Exchange '{exchange}' declared successfully.")
                        self.channel.queue_declare(
                            queue=queue,
                            durable=durable,
                            exclusive=exclusive,
                            auto_delete=auto_delete,
                            arguments=queue_arguments,
                        )
                        self.logger.debug(f"Queue '{queue}' declared successfully.")
                        self.channel.queue_bind(
                            queue=queue,
                            exchange=exchange,
                            routing_key=ifnone(routing_key, default=queue),
                        )
                        return {
                            "status": "success",
                            "message": f"Queue '{queue}' declared successfully and bound to newly declared exchange '{exchange}'.",
                        }
                    else:
                        self.logger.error(
                            f"Exchange '{exchange}' does not exist. Cannot bind queue '{queue}' to it. Use force=True to declare it."
                        )
                        raise ValueError(
                            f"Exchange '{exchange}' does not exist. Cannot bind queue '{queue}' to it. Use force=True to declare it."
                        )
            except ValueError:
                raise
            except Exception as e:
                self.logger.error(f"Failed to declare queue '{queue}': {str(e)}")
                return {"status": "error", "message": f"Failed to declare queue '{queue}': {str(e)}"}
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs):
        """Publish a message to the specified exchange using RabbitMQ.
        Args:
            queue_name: The queue name to use as default routing key.
            message: A Pydantic BaseModel payload.
            exchange: The RabbitMQ exchange to use (from kwargs).
            routing_key: The routing key to use (from kwargs, defaults to queue_name).
            durable: Messages that are not durable are discarded if they cannot be routed to an existing consumer (from kwargs).
            delivery_mode: Use DeliveryMode.Persistent to save messages to disk (from kwargs).
            mandatory: If True, unroutable messages are returned (from kwargs).
        Returns:
            str: The generated job ID for the message.
        """
        channel = self.create_connection()
        job_id = str(uuid.uuid1())
        exchange = kwargs.get("exchange", "default")
        routing_key = kwargs.get("routing_key", queue_name)
        # durable = kwargs.get("durable", True)
        delivery_mode = kwargs.get("delivery_mode", DeliveryMode.Persistent)
        mandatory = kwargs.get("mandatory", True)
        priority = kwargs.get("priority", 0)
        self.logger.info(f"exchange: {exchange}, routing_key: {routing_key}")
        try:
            message_dict = message.model_dump()
            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(message_dict).encode("utf-8"),
                properties=BasicProperties(
                    content_type="application/json",
                    headers={"job_id": job_id, "routing_key": routing_key},
                    delivery_mode=delivery_mode,
                    priority=priority,
                ),
                mandatory=mandatory,
            )
            self.logger.debug(
                f"RabbitMQClient sent message (job_id: {job_id}) "
                f"with routing key: {routing_key} "
                f"to exchange: {exchange}"
            )
            return job_id
        except pika.exceptions.UnroutableError as e:
            self.logger.error("Unroutable Message error: %s \n ", e)
            raise
        except pika.exceptions.ChannelClosedByBroker:
            self.logger.error(f"Channel closed by broker, Check {exchange} existence")
            raise
        except pika.exceptions.ConnectionClosedByBroker:
            self.logger.error("Connection closed by broker. RabbitMQClient failed to publish the message.")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in publish: {e}")
            raise e

    def clean_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Remove all messages from a queue."""
        try:
            self.channel.queue_purge(queue=queue_name)
            return {"status": "success", "message": f"Cleaned queue '{queue_name}'."}
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not clean queue '{queue_name}': {str(e)}")

    def delete_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Delete a queue."""
        try:
            self.channel.queue_delete(queue=queue_name)
            return {"status": "success", "message": f"Deleted queue '{queue_name}'."}
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not delete queue '{queue_name}': {str(e)}")

    def count_exchanges(self, *, exchange: str, **kwargs):
        """Get the number of exchanges in the RabbitMQ server.
        Args:
            exchange: Name of the exchange to check.
        """
        try:
            result = self.channel.exchange_declare(exchange=exchange, passive=True)
            return result
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not count exchanges: {str(e)}")

    def delete_exchange(self, *, exchange: str, **kwargs):
        """Delete an exchange."""
        try:
            self.channel.exchange_delete(exchange=exchange)
            return {"status": "success", "message": f"Deleted exchange '{exchange}'."}
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not delete exchange '{exchange}': {str(e)}")

    def move_to_dlq(
        self,
        source_queue: str,
        dlq_name: str,
        message: pydantic.BaseModel,
        error_details: str,
        **kwargs,
    ):
        """Move a failed message to a dead letter queue"""
        self.logger.info(f"Moving message from {source_queue} to {dlq_name}: {error_details}")
        return None

    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        return self.connection.count_queue_messages(queue_name)
