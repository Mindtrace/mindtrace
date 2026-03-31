import time

from mindtrace.core import EchoInput, EchoOutput, echo_task
from mindtrace.services import EndpointSpec, Service


class EchoService(Service):
    _endpoint_specs = [
        EndpointSpec(path="echo", method_name="echo", schema=echo_task),
    ]

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)
