"""A simple echo task for testing."""

from pydantic import BaseModel

from mindtrace.core.types.task_schema import TaskSchema


class EchoInput(BaseModel):
    message: str
    delay: float = 0.0


class EchoOutput(BaseModel):
    echoed: str


echo_task = TaskSchema(name="echo", input_schema=EchoInput, output_schema=EchoOutput)
