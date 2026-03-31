"""Declarative endpoint specification for Service classes."""

import dataclasses
from typing import Any

from mindtrace.core import TaskSchema


@dataclasses.dataclass(frozen=True)
class EndpointSpec:
    """Static description of a service endpoint.

    Declared as a class-level ``_endpoint_specs`` list on Service subclasses.
    The ``method_name`` is resolved to a bound method at instance init time.

    Example::

        class EchoService(Service):
            _endpoint_specs = [
                EndpointSpec(path="echo", method_name="echo", schema=echo_task),
            ]

            def echo(self, payload: EchoInput) -> EchoOutput:
                return EchoOutput(echoed=payload.message)
    """

    path: str
    method_name: str
    schema: TaskSchema
    methods: tuple[str, ...] = ("POST",)
    scope: str = "public"
    as_tool: bool = False
    autolog_kwargs: dict[str, Any] | None = None
    api_route_kwargs: dict[str, Any] | None = None
