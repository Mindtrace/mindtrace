import uuid
from datetime import datetime

from mindtrace.jobs.types.job_specs import Job, JobSchema


def job_from_schema(schema: JobSchema, input_data) -> Job:
    """Create a Job from a JobSchema and input data.

    This function automatically adds metadata like job ID and creation timestamp.
    Args:
        schema: The JobSchema to use for the job
        input_data: The input data for the job
    Returns:
        Job: A complete Job instance ready for submission
    """

    if isinstance(input_data, schema.input_schema):
        payload = input_data
    else:
        payload = schema.input_schema(**input_data)

    job = Job(
        id=str(uuid.uuid4()),
        name=schema.name,
        schema_name=schema.name,
        payload=payload,
        created_at=datetime.now().isoformat(),
    )

    return job
