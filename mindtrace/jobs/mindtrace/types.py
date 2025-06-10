from pydantic import BaseModel
from typing import Optional
from enum import Enum


class BackendType(str, Enum):
    LOCAL = "local"
    REDIS = "redis"
    RABBITMQ = "rabbitmq"


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    ML_TRAINING = "ml_training"
    OBJECT_DETECTION = "object_detection"
    DATA_PROCESSING = "data_processing"
    CLASSIFICATION = "classification"
    DEFAULT = "default"


class JobInput(BaseModel):
    """Base class for job input data - extend this for specific job types"""

    pass


class JobOutput(BaseModel):
    """Base class for job output data - extend this for specific job types"""

    pass


class JobSchema(BaseModel):
    """A job schema with strongly-typed input and output models"""

    name: str
    input: JobInput
    output: Optional[JobOutput] = None


class Job(BaseModel):
    """A job instance ready for execution - system routes based on job_type"""

    id: str
    name: str
    job_type: JobType = JobType.DEFAULT
    payload: JobSchema
    status: ExecutionStatus = ExecutionStatus.QUEUED
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    entrypoint: Optional[str] = None

    # User can optionally specify priority for job processing
    priority: Optional[int] = None


# Queue mapping for automatic routing
QUEUE_MAPPING = {
    JobType.ML_TRAINING: "ml_training_jobs",
    JobType.OBJECT_DETECTION: "detection_jobs",
    JobType.DATA_PROCESSING: "data_jobs",
    JobType.CLASSIFICATION: "classification_jobs",
    JobType.DEFAULT: "default_jobs",
}
