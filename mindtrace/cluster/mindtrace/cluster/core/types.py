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

class WorkerRunInput(BaseModel):
    job_dict: dict

class WorkerRunOutput(BaseModel):
    status: str
    output: Any

WorkerRunTaskSchema = TaskSchema(name="worker_run", input_schema=WorkerRunInput, output_schema=WorkerRunOutput)

class ConnectToBackendInput(BaseModel):
    backend_args: dict
    queue_name: str


ConnectToBackendTaskSchema = TaskSchema(name="connect_to_backend", input_schema=ConnectToBackendInput)

class RegisterJobToWorkerInput(BaseModel):
    job_type: str
    worker_url: str

RegisterJobToWorkerTaskSchema = TaskSchema(name="register_job_to_worker", input_schema=RegisterJobToWorkerInput)