from pydantic import BaseModel

from mindtrace.services import Service, TaskSchema


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    echoed: str


echo_task = TaskSchema(
    name="echo",
    input_schema=EchoInput,
    output_schema=EchoOutput,
)


class EchoService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, task=echo_task)

    def echo(self, payload: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=payload.message)
