import time

from mindtrace.core import EchoInput, EchoOutput, echo_task
from mindtrace.services import Service


class EchoService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_task)

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)
