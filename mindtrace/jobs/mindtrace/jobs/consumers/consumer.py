from abc import abstractmethod
from typing import Optional

from mindtrace.core import Mindtrace
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.types.job_specs import JobSchema
from mindtrace.jobs.orchestrator import Orchestrator


class Consumer(Mindtrace):
    """Base class for processing jobs from queues.
    
    Automatically creates the appropriate consumer backend when connected to an orchestrator.
    Consumers receive job data as dict objects for processing.
    """
    
    def __init__(self, job_type_name: str):
        super().__init__()
        self.job_type_name = job_type_name
        self.orchestrator: Optional[Orchestrator] = None
        self.consumer_backend: Optional[ConsumerBackendBase] = None
        self.job_schema: Optional[JobSchema] = None
        self.queue_name: Optional[str] = None
    
    def connect_to_orchestrator(self, orchestrator: Orchestrator) -> None:
        """Connect to orchestrator and create the appropriate consumer backend."""
        if self.orchestrator:
            raise RuntimeError("Consumer already connected.")
        
        self.orchestrator = orchestrator
        
        schema_info = orchestrator.get_schema_for_job_type(self.job_type_name)
        if not schema_info:
            raise ValueError(f"No schema registered for job type: {self.job_type_name}")
        
        self.job_schema = schema_info['schema']
        self.queue_name = schema_info['queue_name']
        
        self.consumer_backend = orchestrator.create_consumer_backend_for_schema(self.job_schema)
        self.consumer_backend.set_run_method(self.run)
    
    def consume(self, num_messages: int = 0, queues: str | list[str] | None = None, block: bool = True) -> None:
        """Consume messages from the queue.
        
        Args:
            num_messages: Number of messages to process. If 0, runs indefinitely.
            queues: Queue(s) to consume from. If None, uses the consumer's default queue.
            block: Whether to block when no messages are available.
        """
        if not self.consumer_backend:
            raise RuntimeError("Consumer not connected. Call connect() first.")
        
        self.consumer_backend.consume(num_messages, queues=queues, block=block)
    
    def consume_until_empty(self, queues: str | list[str] | None = None, block: bool = True) -> None:
        """Consume messages until all specified queues are empty.
        
        Args:
            queues: Queue(s) to consume from. If None, uses the consumer's default queue.
            block: Whether to block when no messages are available.
        """
        if not self.consumer_backend:
            raise RuntimeError("Consumer not connected. Call connect() first.")
        
        self.consumer_backend.consume_until_empty(queues=queues, block=block)
    
    @abstractmethod
    def run(self, job_dict: dict) -> dict:
        """Process a single job. Must be implemented by subclasses.
        
        Args:
            job_dict: Dict containing job data including 'input_data' with the job inputs
            
        Returns:
            dict: Processing results
        """
        pass