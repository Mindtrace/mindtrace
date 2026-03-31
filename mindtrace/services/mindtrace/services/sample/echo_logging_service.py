import time

from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import EndpointSpec, Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware


class EchoInput(BaseModel):
    message: str
    delay: float = 0.0


class EchoOutput(BaseModel):
    echoed: str


echo_task = TaskSchema(name="echo", input_schema=EchoInput, output_schema=EchoOutput)


class EchoService(Service):
    _endpoint_specs = [
        EndpointSpec(path="echo", method_name="echo", schema=echo_task),
    ]

    def __init__(self, *args, use_structlog=True, **kwargs):
        # Add use_structlog to kwargs to pass to parent Mindtrace class
        kwargs["use_structlog"] = use_structlog
        super().__init__(*args, **kwargs)
        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)
