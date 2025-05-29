from pydantic import BaseModel
from typing import Dict, List, Optional, Any
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
    name: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    test_case: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    version: str = "1.0.0"

class JobDefinition(BaseModel):
    schema_name: str  # References a JobSchema
    inputs: Dict[str, Any]  # Must conform to schema's input_schema
    config: Optional[Dict[str, Any]] = {}
    resources: Optional[Dict[str, Any]] = {}
    metadata: Optional[Dict[str, str]] = {}

class JobExecution(BaseModel):
    """Represents a job actually running on the cluster"""
    id: str
    queue_id: str  
    backend: BackendType
    status: ExecutionStatus
    definition: JobDefinition
    worker_id: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class JobValidationResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    estimated_cost: Optional[float] = None
    estimated_duration: Optional[str] = None

class Job(BaseModel):
    id: str
    schema_name: str
    definition: JobDefinition
    created_at: str
    updated_at: str