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
    """A job instance ready for execution - system routes based on schema_name"""
    id: str
    name: str
    schema_name: str  # References the JobSchema this job uses
    payload: JobSchema
    status: ExecutionStatus = ExecutionStatus.QUEUED
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    entrypoint: Optional[str] = None
    priority: Optional[int] = None
    input_data: Optional[dict] = None
