import time
from typing import TYPE_CHECKING

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.local.client import LocalClient


class LocalConsumerBackend(ConsumerBackendBase):
    """Local in-memory consumer backend."""

    def __init__(
        self,
        queue_name: str,
        consumer_frontend,
        orchestrator: "LocalClient",
        poll_timeout: float = 1,
        failure_policy: ConsumerFailurePolicy | str = ConsumerFailurePolicy.DISCARD,
    ):
        super().__init__(queue_name, consumer_frontend)
        self.failure_policy = ConsumerFailurePolicy(failure_policy)
        if self.failure_policy is not ConsumerFailurePolicy.DISCARD:
            raise NotImplementedError(
                f"Local consumer backend does not support failure policy '{self.failure_policy.value}'. Use 'discard'."
            )
        self.poll_timeout = poll_timeout
        self.orchestrator = orchestrator
        self.queues = [queue_name] if queue_name else []

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume messages from the local queue(s)."""
        self._ensure_open()
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        messages_attempted = 0

        try:
            while not self.stopped and (num_messages == 0 or messages_attempted < num_messages):
                no_messages_found = True
                for queue in queues:
                    if self.stopped or (num_messages > 0 and messages_attempted >= num_messages):
                        break
                    try:
                        message = self.orchestrator.receive_message(queue, block=block, timeout=self.poll_timeout)
                        if message:
                            no_messages_found = False
                            messages_attempted += 1
                            self.process_message(message)
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
        self._ensure_open()
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        while not self.stopped and any(self.orchestrator.count_queue_messages(q) > 0 for q in queues):
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
