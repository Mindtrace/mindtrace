from typing import Type

from pydantic import BaseModel

from mindtrace.services import Gateway
from mindtrace.core import JobSchema, Job
from mindtrace.jobs import Orchestrator
from mindtrace.registry import Registry, BaseMaterializer
from mindtrace.cluster.core.worker_base import Worker, WorkerConnectionManager
from mindtrace.cluster.core.node import NodeConnectionManager
from mindtrace.cluster.mindtrace.cluster.core.types import JobStatus, node_id, worker_id, worker_registry_key, job_registry_key, worker_maintenance_id, job_id

class ClusterManager(Gateway):
    orchestrator: Orchestrator
    worker_registry: Registry[Worker]
    job_registry: Registry[JobSchema]
    nodes: dict[node_id, NodeConnectionManager] 
    workers: dict[worker_id, WorkerConnectionManager] 
    gateway_job_types: dict[job_registry_key, str] # str here is endpoint URL
    orchestrator_job_types: set[job_registry_key] # or could just send anything that's not in gateway_job_types to Orchestrator
    monitored_jobs: dict[job_id, worker_id]

    def __init__(self, url):
        raise NotImplemented
    
    # Authentication methods

    # Gateway method
    def register_app(self, name: str, url: str):
        # makes the app endpoints available at self.url + name + endpoint
        raise NotImplemented
    
    # Worker Registry
    def register_worker(self, name: str, worker, materializer: Type[BaseMaterializer]):
        # add worker to worker_registry
        # worker may not be a concrete Worker, instead something that is Materializable
        # and instantiates to a concrete Worker
        raise NotImplemented
    
    # Registering jobs to job_registry 
    def register_job_to_endpoint(self, job_type: JobSchema, endpoint: str):
        # adds to gateway_jobs
        raise NotImplemented

    def connect_worker(self, worker: WorkerConnectionManager, job_type: JobSchema):
        # adds to orchestrator_jobs 
        # could be option for direct connection here too?
        raise NotImplemented
    
    def register_job_to_worker_type(self, job_type: JobSchema, worker_type: worker_id):
        # adds to orchestrator_jobs
        raise NotImplemented
    
    # Generic method for submitting all jobs
    def submit(self, job: Job, blocking: bool = False) -> BaseModel | job_id:
        if job.job_type in self.gateway_job_types:
            if not blocking:
                raise RuntimeError
            raise NotImplemented # send job to endpoint
        elif job.job_type in self.orchestrator_job_types:
            return self.orchestrator.submit(job, blocking)
        else:
            raise ValueError

    # Job queries
    def job_status(self, job_id: job_id) -> JobStatus:
        raise NotImplemented
    
    def job_result(self, job_id: job_id) -> BaseModel:
        raise NotImplemented

    # Cluster managed Workers
    def launch_worker(self, node_id: node_id | any, worker_type: worker_registry_key) -> worker_id:
        # and automatically connect it to self.orchestrator
        if node_id is any:
            raise NotImplemented # really not for a while
        raise NotImplemented
    
    def maintain_worker(self, node_id: node_id | any, worker_type: worker_registry_key, count: int = 1) -> worker_maintenance_id:
        # and automatically connect it to self.orchestrator
        if node_id is any:
            raise NotImplemented # really not for a while
        raise NotImplemented
    
    def maintained_workers(self, maintenance_id: worker_maintenance_id) -> list[worker_id]:
        raise NotImplemented
    
    # General Worker methods
    def connected_workers(self, node_id: node_id | None = None) -> list[worker_id]:
        # if node_id is None, get all workers at all nodes
        raise NotImplemented
    
    def shutdown_worker(self, worker_id: worker_id):
        raise NotImplemented
    
    def shutdown_all_workers(self, node_id: node_id):
        raise NotImplemented
    
    # Node commands
    def connect_node(self, node: NodeConnectionManager) -> node_id:
        raise NotImplemented
    
    def disconnect_node(self, node_id: node_id):
        raise NotImplemented
    
    def list_nodes(self) -> list[node_id]:
        return list(self.nodes.keys())
    
    ## Scheduled processes - run every n minutes independent of Fast API
    def check_job_status(self, job_id: job_id):
        # e.g. if the worker is down then notify?
        raise NotImplemented

    def check_worker_status(self, worker_id: worker_id):
        # for maintained workers - if this worker is down, launch a replacement
        raise NotImplemented
        

