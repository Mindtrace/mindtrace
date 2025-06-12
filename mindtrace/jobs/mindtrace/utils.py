import uuid
from datetime import datetime
from typing import Any
from .types import Job, JobSchema, JobInput
def ifnone(val: Any, default: Any) -> Any:
    """Return default if val is None, otherwise return val."""
    return default if val is None else val
def job_from_schema(schema: JobSchema, input_data: JobInput) -> Job:
    """
    Create a Job from a JobSchema and input data.
    This function automatically adds metadata like job ID and creation timestamp.
    Args:
        schema: The JobSchema to use for the job
        input_data: The input data for the job
    Returns:
        Job: A complete Job instance ready for submission
    """
    job = Job(
        id=str(uuid.uuid4()),
        name=schema.name,
        schema_name=schema.name,
        payload=JobSchema(
            name=schema.name,
            input=input_data,
            output=schema.output
        ),
        created_at=datetime.now().isoformat()
    )
    
    job.input_data = input_data.model_dump()
    return job
