from typing import NewType

from mindtrace.services import Service
from mindtrace.registry import Registry
from mindtrace.cluster.core.worker_base import Worker, WorkerConnectionManager
from mindtrace.cluster.mindtrace.cluster.core.types import worker_registry_key, any, worker_id

class Node(Service):
    _worker_registry: Registry[Worker]
    _workers: dict[worker_id, WorkerConnectionManager]
    def __init__(self):
        raise NotImplemented
    
    # Cluster methods - can do here or on ClusterConnectionManager, the result is the same
    def connect_to_cluster(self, url: str):
        raise NotImplemented
    
    def disconnect(self):
        raise NotImplemented
    
    # Node-managed workers
    def register_worker(self, worker: worker_registry_key | list[worker_registry_key] | any):
        # connect to Cluster worker registry and pull the listed workers
        # or possibly just tell the Cluster that and pull when required?
        raise NotImplemented
    
    def launch_worker(self, worker: worker_registry_key) -> worker_id:
        raise NotImplemented
    
    # Externally-managed workers
    def connect_worker(self, worker: Worker | WorkerConnectionManager) -> worker_id:
        raise NotImplemented
    
    # General tasks
    def list_workers(self) -> list[worker_id]:
        raise NotImplemented
    
    def get_worker(self, worker_id: worker_id) -> WorkerConnectionManager:
        raise NotImplemented

    def shutdown_worker(self, worker_id: worker_id):
        raise NotImplemented
    
    def shutdown_all_workers(self):
        raise NotImplemented
    
    def heartbeat(self):
        # Overrides default, also provides information on workers
        raise NotImplemented
    



