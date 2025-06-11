from abc import abstractmethod
from typing import Optional
from mindtrace.core.mindtrace.core import MindtraceABC
from mindtrace.jobs.mindtrace.queue_management.orchestrator import Orchestrator
from mindtrace.jobs.mindtrace.queue_management.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job, JobSchema


class Consumer(MindtraceABC):
    """
    Automatically creates the appropriate backend-specific ConsumerBackend when connected to an Orchestrator.
    
    Args:
        job_type_name (str): The name of the job type to consume.
    """
    
    def __init__(self, job_type_name: str):
        super().__init__()
        self.job_type_name = job_type_name
        self.orchestrator: Optional[Orchestrator] = None
        self.consumer_backend: Optional[ConsumerBackendBase] = None
        self.job_schema: Optional[JobSchema] = None
        self.queue_name: Optional[str] = None
    
    def connect(self, orchestrator: Orchestrator) -> None:
        """Connect to orchestrator and automatically create backend-specific ConsumerBackend."""
        self.orchestrator = orchestrator
        
        schema_info = orchestrator.get_schema_for_job_type(self.job_type_name)
        if not schema_info:
            raise ValueError(f"No schema registered for job type: {self.job_type_name}")
        
        self.job_schema = schema_info['schema']
        self.queue_name = schema_info['queue_name']
        
        self.consumer_backend = orchestrator.create_consumer_backend_for_schema(self.job_schema)
        self.consumer_backend.set_message_processor(self.run)
    
    def consume(self, num_messages: Optional[int] = None) -> None:
        """Consume messages indefinitely (or up to num_messages).
        
        This delegates to the backend-specific ConsumerBackend which implements
        optimized consumption strategies for each backend type.
        """
        if not self.consumer_backend:
            raise RuntimeError("Consumer not connected. Call connect() first.")
        
        self.consumer_backend.consume_messages(num_messages)
    
    @abstractmethod
    def run(self, job: Job) -> None:
        """Process a single job. Must be implemented by subclasses.
        
        This method is called by the ConsumerBackend when a message is received.
        """
        pass