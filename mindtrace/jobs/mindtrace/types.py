from pydantic import BaseModel
from typing import Dict, Optional, Any
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

class JobSchema(BaseModel):
    """A job schema that can handle input and output directly"""
    name: str
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = {}
    metadata: Optional[Dict[str, str]] = {}
    description: Optional[str] = None
    version: str = "1.0.0"

class Job(BaseModel):
    """A job instance ready for execution"""
    id: str
    job_schema: JobSchema
    status: ExecutionStatus = ExecutionStatus.QUEUED
    backend: Optional[BackendType] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None