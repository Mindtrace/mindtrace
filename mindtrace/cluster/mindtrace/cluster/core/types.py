from typing import Any

from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.jobs import Job


class JobOutput(BaseModel):
    status: str
    output: Any


class SubmitJobTaskSchema(TaskSchema):
    name: str = "submit_job"
    input_schema: type[Job] = Job
    output_schema: type[JobOutput] = JobOutput


class RegisterJobToEndpointInput(BaseModel):
    job_type: str
    endpoint: str


class RegisterJobToEndpointTaskSchema(TaskSchema):
    name: str = "register_job_to_endpoint"
    input_schema: type[RegisterJobToEndpointInput] = RegisterJobToEndpointInput
