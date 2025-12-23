from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from mindtrace.database import UnifiedMindtraceDocument


class ProxyWorker(BaseModel):
    worker_type: str
    git_repo_url: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    git_working_dir: str | None = None
    worker_params: dict


class JobStatus(UnifiedMindtraceDocument):
    job_id: str = Field(description="Job's id")
    worker_id: str = Field(description="Worker's id")
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


class WorkerAutoConnect(UnifiedMindtraceDocument):
    worker_type: str = Field(description="Worker type")
    schema_name: str = Field(description="Schema name")

    class Meta:
        collection_name = "worker_auto_connect"
        global_key_prefix = "cluster"
        use_cache = False
        indexed_fields = ["worker_type"]
        unique_fields = ["worker_type"]


class WorkerStatusEnum(Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    SHUTDOWN = "shutdown"
    NONEXISTENT = "nonexistent"


class WorkerStatus(UnifiedMindtraceDocument):
    worker_id: str = Field(description="Worker id")
    worker_type: str = Field(description="Worker type")
    worker_url: str = Field(description="Worker url")
    job_id: str | None = Field(description="Job id")
    status: WorkerStatusEnum = Field(description="Worker status")
    last_heartbeat: datetime | None = Field(description="Last heartbeat")

    class Meta:
        collection_name = "worker_status"
        global_key_prefix = "cluster"
        use_cache = False
        indexed_fields = ["worker_id", "worker_url"]
        unique_fields = ["worker_id"]


class NodeWorker(UnifiedMindtraceDocument):
    worker_type: str = Field(description="Worker type")
    worker_port: int = Field(description="Worker port")
    worker_id: str = Field(description="Worker id")
    worker_name: str = Field(description="Worker name")
    worker_url: str = Field(description="Worker url")

    class Meta:
        collection_name = "node_worker"
        global_key_prefix = "cluster"
        use_cache = False
        indexed_fields = ["worker_port", "worker_id", "worker_name"]
        unique_fields = ["worker_id"]


class WorkerStatusLocal(UnifiedMindtraceDocument):
    worker_id: str = Field(description="Worker id")
    status: WorkerStatusEnum = Field(description="Worker status")
    job_id: str | None = Field(description="Job id")

    class Meta:
        collection_name = "worker_status_local"
        global_key_prefix = "cluster"
        use_cache = False
        indexed_fields = ["worker_id"]
        unique_fields = ["worker_id"]


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
    worker_name: str | None = None
    worker_url: str | None = None


class LaunchWorkerOutput(BaseModel):
    worker_id: str
    worker_name: str
    worker_url: str


class RegisterNodeInput(BaseModel):
    node_url: str


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
    job_type: str | None = None
    git_repo_url: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    git_working_dir: str | None = None


class ClusterLaunchWorkerInput(BaseModel):
    node_url: str
    worker_type: str
    worker_name: str | None = None
    worker_url: str | None = None


class ClusterLaunchWorkerOutput(BaseModel):
    worker_id: str
    worker_name: str
    worker_url: str


class ClusterRegisterJobToWorkerInput(BaseModel):
    job_type: str
    worker_url: str


class RegisterJobSchemaToWorkerTypeInput(BaseModel):
    job_schema_name: str
    worker_type: str


class GetWorkerStatusInput(BaseModel):
    worker_id: str


class GetWorkerStatusByUrlInput(BaseModel):
    worker_url: str


class QueryWorkerStatusInput(BaseModel):
    worker_id: str


class QueryWorkerStatusByUrlInput(BaseModel):
    worker_url: str


class ClearJobSchemaQueueInput(BaseModel):
    job_schema_name: str


class ShutdownWorkerInput(BaseModel):
    worker_name: str


class ShutdownWorkerByIdInput(BaseModel):
    worker_id: str


class ShutdownWorkerByPortInput(BaseModel):
    worker_port: int
