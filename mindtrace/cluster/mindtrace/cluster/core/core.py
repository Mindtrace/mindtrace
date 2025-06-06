from enum import Enum
from typing import NewType, NamedTuple


node_id = NewType("node_id", str)
worker_id = NewType("worker_id", str)
worker_registry_key = NewType("worker_registry_key", str)
job_registry_key = NewType("job_registry_key", str)
job_id = NewType("job_id", str)
worker_maintenance_id = NewType("worker_maintenance_id", str)
any = NewType("any", None)

class JobStatus(Enum):
    RUNNING = 0
    SUCCESS = 1
    FAIL = 2

class WorkerStatusEnum(Enum):
    IDLE = 0
    RUNNING = 1
    ERROR = 2

class WorkerStatus(NamedTuple):
    status: WorkerStatusEnum
    job_id: job_id | None