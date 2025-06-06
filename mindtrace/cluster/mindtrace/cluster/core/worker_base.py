from pydantic import BaseModel

from mindtrace.jobs import Consumer
from mindtrace.services import Service
from mindtrace.cluster.core.core import WorkerStatus, JobStatus, job_id

class Worker(Consumer, Service): # Consumer is ABC so Worker is too as we don't override run()
    def connect_to_cluster(self, url: str):
        # also connects (via Consumer.connect) to Cluster.orchestrator
        raise NotImplemented
    
    def start(self):
        raise NotImplemented

    def status(self) -> WorkerStatus:
        raise NotImplemented
    
    def job_status(self, job_id: job_id) -> JobStatus:
        raise NotImplemented
    
    def job_result(self, job_id: job_id) -> BaseModel:
        raise NotImplemented

