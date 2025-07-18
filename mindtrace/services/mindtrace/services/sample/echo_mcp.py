import time

from mindtrace.core import TaskSchema
from mindtrace.services import Service
from pydantic import BaseModel


class EchoInput(BaseModel):
    message: str
    delay: float = 0.0


class EchoOutput(BaseModel):
    echoed: str


class EchoTaskSchema(TaskSchema):
    name: str = "echo"
    input_schema: type[EchoInput] = EchoInput
    output_schema: type[EchoOutput] = EchoOutput


echo_task = EchoTaskSchema()


# Example: Adding a tool directly using add_tool

def reverse_message(payload: EchoInput) -> EchoOutput:
    """A demo tool that reverses the input message."""
    reversed_msg = payload.message[::-1]
    return EchoOutput(echoed=reversed_msg)

class EchoService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_task, as_tool = True)
        # Add the reverse_message tool directly (not as an endpoint)
        self.add_tool("reverse_message", reverse_message)

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)
