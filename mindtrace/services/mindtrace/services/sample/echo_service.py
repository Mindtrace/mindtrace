import time

from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service


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


class EchoService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_task)

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)
