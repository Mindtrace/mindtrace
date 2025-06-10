import json
import time
import uuid
import logging
from typing import Optional
import pydantic
import pika
from pika import BasicProperties, DeliveryMode

from mindtrace.jobs.mindtrace.queue_management.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.mindtrace.queue_management.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.mindtrace.utils import ifnone
from mindtrace.jobs.mindtrace.types import Job


class RabbitMQClient(OrchestratorBackend):
    def __init__(self, host: str = None, port: int = None, username: str = None, password: str = None):
        """Initialize the RabbitMQ client with connection parameters.

        Args:
            host: RabbitMQ server hostname.
            port: RabbitMQ server port.
            username: Username for RabbitMQ authentication.
            password: Password for RabbitMQ authentication.
        """
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.connection = RabbitMQConnection(host=host, port=port, username=username, password=password)
        self.connection.connect()
        self.channel = self.connection.get_channel()

    def declare_exchange(
        self, exchange: str, exchange_type: str = "direct", durable: bool = True, auto_delete: bool = False
    ):
        """Declare a RabbitMQ exchange.

        Args:
            exchange: Name of the exchange to declare.
            exchange_type: Type of the exchange (e.g., 'direct', 'topic', 'fanout').
            durable: Make the exchange durable.
            auto_delete: Automatically delete the exchange when no queues are bound.
        """
        try:
            self.channel.exchange_declare(exchange=exchange, passive=True)  # Raises exception if exchange doesn't exist
            self.logger.debug(f"Exchange '{exchange}' already exists. Not declaring it again.")
            return {"status": "success", "message": f"Exchange '{exchange}' already exists. Not declaring it again."}

        except pika.exceptions.ChannelClosedByBroker:
            try:
                self.channel = self.connection.get_channel()  # Re-establish channel after it was closed
                self.channel.exchange_declare(
                    exchange=exchange, exchange_type=exchange_type, durable=durable, auto_delete=auto_delete
                )
                self.logger.debug(f"Exchange '{exchange}' declared successfully.")
                return {"status": "success", "message": f"Exchange '{exchange}' declared successfully."}
            except Exception as e:
                raise RuntimeError(f"Could not declare exchange '{exchange}': {str(e)}")

    def declare_queue(self, queue_name: str, **kwargs):
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

        queue = queue_name
        exchange = kwargs.get('exchange')
        durable = kwargs.get('durable', True)
        exclusive = kwargs.get('exclusive', False)
        auto_delete = kwargs.get('auto_delete', False)
        routing_key = kwargs.get('routing_key')
        force = kwargs.get('force', False)
        max_priority = kwargs.get('max_priority')

        queue_arguments = {}
        if max_priority is not None:
            queue_arguments['x-max-priority'] = max_priority

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
                        queue=queue, durable=durable, exclusive=exclusive, auto_delete=auto_delete, arguments=queue_arguments
                    )
                    self.logger.debug(f"Queue '{queue}' declared successfully.")
                    self.channel.queue_bind(
                        queue=queue, exchange=exchange, routing_key=ifnone(routing_key, default=queue)
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
                            queue=queue, durable=durable, exclusive=exclusive, auto_delete=auto_delete, arguments=queue_arguments
                        )
                        self.logger.debug(f"Queue '{queue}' declared successfully.")
                        self.channel.queue_bind(
                            queue=queue, exchange=exchange, routing_key=ifnone(routing_key, default=queue)
                        )
                        return {
                            "status": "success",
                            "message": f"Queue '{queue}' declared successfully and bound to newly declared exchange '{exchange}'.",
                        }
                    else:
                        self.logger.error(
                            f"Exchange '{exchange}' does not exist. Cannot bind queue '{queue}' to it. Use force=True to declare it."
                        )
                        raise ValueError(f"Exchange '{exchange}' does not exist. Cannot bind queue '{queue}' to it. Use force=True to declare it.")

            except Exception as e:
                self.logger.error(f"Failed to declare queue '{queue}': {str(e)}")
                raise RuntimeError(f"Failed to declare queue '{queue}': {str(e)}")

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
        if not self.connection.is_connected():  # Reconnect if the connection was lost or timed out
            self.connection.connect()
            self.channel.confirm_delivery()

        if self.channel is None or self.channel.is_closed:
            self.channel = self.connection.get_channel()

        if self.channel is not None:
            job_id = str(uuid.uuid1())
            exchange = kwargs.get('exchange', '')
            routing_key = kwargs.get('routing_key', queue_name)
            durable = kwargs.get('durable', True)
            delivery_mode = kwargs.get('delivery_mode', DeliveryMode.Persistent)
            mandatory = kwargs.get('mandatory', True)
            priority = kwargs.get('priority', 0)
            
            self.logger.info(f"exchange: {exchange}, routing_key: {routing_key}")
            
            try:
                # Convert the pydantic model to dict and then to JSON
                message_dict = message.model_dump()
                
                # Publish the message
                self.channel.basic_publish(
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
                self.logger.error(
                    f"Connection closed by broker. RabbitMQClient failed to publish the message."
                )
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error in publish: {e}")
                raise e
        else:
            self.logger.error(f"RabbitMQClient failed to obtain a channel for publishing the message.")
            raise pika.exceptions.ChannelError("Failed to obtain a channel for publishing the message")

    def receive_message(self, queue_name: str, **kwargs) -> Optional[pydantic.BaseModel]:
        """Retrieve a message from a specified RabbitMQ queue, returning full message details.

        This method uses RabbitMQ's basic_get method to fetch a message. It supports blocking behavior by polling until
        a message is available or the timeout is reached.

        Args:
            queue_name: The name of the queue from which to receive the message.
            block: Whether to block until a message is available.
            timeout: Maximum time in seconds to block if no message is available.
            auto_ack: Whether to automatically acknowledge the message upon retrieval.
            **kwargs: Additional keyword arguments to pass to basic_get (if any).

        Returns:
            Optional[pydantic.BaseModel]: On success, returns a Job object. On failure or timeout, returns None.
        """
        if not self.connection.is_connected():
            self.connection.connect()
        
        if self.channel is None or self.channel.is_closed:
            self.channel = self.connection.get_channel()
        
        # Extract parameters from kwargs with defaults
        block = kwargs.get('block', False)
        timeout = kwargs.get('timeout', None)
        auto_ack = kwargs.get('auto_ack', True)
        
        try:
            if block:
                start_time = time.time()
                while True:
                    # basic_get returns a tuple (method_frame, header_frame, body)
                    method_frame, header_frame, body = self.channel.basic_get(queue=queue_name, auto_ack=auto_ack, **kwargs)
                    if method_frame:
                        self.logger.info(f"Received message from queue '{queue_name}'.")
                        # Parse JSON back to dict and create Job object
                        message_dict = json.loads(body.decode('utf-8'))
                        return Job(**message_dict)
                    
                    if timeout is not None and (time.time() - start_time) > timeout:
                        self.logger.warning(f"Timeout reached while waiting for a message from queue '{queue_name}'.")
                        return None
                    time.sleep(0.1)
            else:
                method_frame, header_frame, body = self.channel.basic_get(queue=queue_name, auto_ack=auto_ack, **kwargs)
                if method_frame:
                    self.logger.info(f"Received message from queue '{queue_name}'.")
                    # Parse JSON back to dict and create Job object
                    message_dict = json.loads(body.decode('utf-8'))
                    return Job(**message_dict)
                else:
                    self.logger.debug(f"No message available in queue '{queue_name}'.")
                    return None
        except Exception as e:
            self.logger.error(f"Error receiving message from queue '{queue_name}': {str(e)}")
            raise RuntimeError(f"Error receiving message from queue '{queue_name}': {str(e)}")

    def clean_queue(self, queue_name: str, **kwargs) -> None:
        """Remove all messages from a queue."""
        try:
            self.channel.queue_purge(queue=queue_name)
            return {"status": "success", "message": f"Cleaned queue '{queue_name}'."}
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not clean queue '{queue_name}': {str(e)}")
        
    def delete_queue(self, queue_name: str, **kwargs) -> None:
        """Delete a queue."""
        try:
            self.channel.queue_delete(queue=queue_name)
            return {"status": "success", "message": f"Deleted queue '{queue_name}'."}
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not delete queue '{queue_name}': {str(e)}")

    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        """Get the number of messages in a queue."""
        try:
            result = self.channel.queue_declare(
                queue=queue_name, durable=True, exclusive=False, auto_delete=False, passive=True
            )
            return result.method.message_count
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not count messages in queue '{queue_name}': {str(e)}")

    def count_exchanges(self, exchange: str):
        """Get the number of exchanges in the RabbitMQ server.

        Args:
            exchange: Name of the exchange to check.
        """
        try:
            result = self.channel.exchange_declare(exchange=exchange, passive=True)
            return result
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not count exchanges: {str(e)}")

    def delete_exchange(self, exchange: str, **kwargs):
        """Delete an exchange."""
        try:
            self.channel.exchange_delete(exchange=exchange)
            return {"status": "success", "message": f"Deleted exchange '{exchange}'."}
        except pika.exceptions.ChannelClosedByBroker as e:
            raise ConnectionError(f"Could not delete exchange '{exchange}': {str(e)}")

    # DLQ Methods - TODO: Implement
    def move_to_dlq(self, source_queue: str, dlq_name: str, message: pydantic.BaseModel, error_details: str, **kwargs):
        """Move a failed message to a dead letter queue"""
        pass