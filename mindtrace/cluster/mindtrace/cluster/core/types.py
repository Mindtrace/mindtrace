from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from mindtrace.database import UnifiedMindtraceDocument


class JobStatus(UnifiedMindtraceDocument):
    job_id: str = Field(description="Job's id")
    worker_id: str | None = Field(description="Worker's id")
    status: str = Field(description="Job's status")
    output: Any = Field(description="Job's output")

    class Meta:
        collection_name = "job_status"
        global_key_prefix = "cluster"
        use_cache = False
        indexed_fields = ["job_id"]
        unique_fields = ["job_id"]


class JobSchemaTargeting(UnifiedMindtraceDocument):
    schema_name: str = Field(description="Schema name")
    target_endpoint: str = Field(description="Target endpoint")

    class Meta:
        collection_name = "job_schema_targeting"
        global_key_prefix = "cluster"
        use_cache = False
        indexed_fields = ["schema_name"]
        unique_fields = ["schema_name"]


class WorkerStatusEnum(Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class RegisterJobToEndpointInput(BaseModel):
    job_type: str
    endpoint: str


class WorkerRunInput(BaseModel):
    job_dict: dict


class ConnectToBackendInput(BaseModel):
    backend_args: dict
    queue_name: str
    cluster_url: str


class RegisterJobToWorkerInput(BaseModel):
    job_type: str
    worker_url: str


class GetJobStatusInput(BaseModel):
    job_id: str


class WorkerAlertStartedJobInput(BaseModel):
    job_id: str
    worker_id: str


class WorkerAlertCompletedJobInput(BaseModel):
    job_id: str
    status: str
    output: dict
    worker_id: str


class LaunchWorkerInput(BaseModel):
    worker_type: str
    worker_url: str


class RegisterNodeInput(BaseModel):
    node_id: str


class RegisterNodeOutput(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str


class RegisterWorkerTypeInput(BaseModel):
    worker_name: str
    worker_class: str
    worker_params: dict
    materializer_name: str | None = None
