import time
from typing import TYPE_CHECKING

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.local.client import LocalClient


class LocalConsumerBackend(ConsumerBackendBase):
    """Local in-memory consumer backend."""

    def __init__(self, queue_name: str, consumer_frontend, orchestrator: "LocalClient", poll_timeout: float = 1):
        super().__init__(queue_name, consumer_frontend)
        self.poll_timeout = poll_timeout
        self.orchestrator = orchestrator
        self.queues = [queue_name] if queue_name else []

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume messages from the local queue(s)."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        messages_consumed = 0

        try:
            while num_messages == 0 or messages_consumed < num_messages:
                no_messages_found = True
                for queue in queues:
                    try:
                        message = self.orchestrator.receive_message(queue, block=block, timeout=self.poll_timeout)
                        if message:
                            no_messages_found = False
                            try:
                                self.process_message(message)
                                messages_consumed += 1
                            except Exception as process_error:
                                self.logger.debug(f"Error processing message from queue {queue}: {process_error}")
                                messages_consumed += 1
                    except Exception as e:
                        self.logger.debug(f"Error consuming from queue {queue}: {e}")
                        if block is False:
                            return
                        time.sleep(1)

                if no_messages_found and block is False:
                    return

                if no_messages_found and block is True:
                    time.sleep(0.1)

        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")

    def consume_until_empty(self, *, queues: str | list[str] | None = None, block: bool = True, **kwargs) -> None:
        """Consume messages from the queue(s) until empty."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        while any(self.orchestrator.count_queue_messages(q) > 0 for q in queues):
            self.consume(num_messages=1, queues=queues, block=block)

    def process_message(self, message) -> bool:
        """Process a single message."""
        if isinstance(message, dict):
            try:
                self.consumer_frontend.run(message)
                job_id = message.get("id", "unknown")
                self.logger.debug(f"Successfully processed dict job {job_id}")
                return True
            except Exception as e:
                job_id = message.get("id", "unknown")
                self.logger.error(f"Error processing dict job {job_id}: {str(e)}")
                return False
        else:
            self.logger.warning(f"Received non-dict message: {type(message)}")
            self.logger.debug(f"Message content: {message}")
            return False
