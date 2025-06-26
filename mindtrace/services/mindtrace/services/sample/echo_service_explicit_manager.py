import time
from typing import Literal

from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service, ConnectionManager, make_method

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

class EchoConnectionManager(ConnectionManager):
    _echo, aecho = make_method("/echo", EchoInput, EchoOutput)
    def echo(self, message: str, delay: float = 0.0, **kwargs) -> EchoOutput:
        return self._echo(message=message, delay=delay, **kwargs)

class EchoServiceWithManager(Service[EchoConnectionManager]):
    _client_interface = EchoConnectionManager
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_task)

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)
