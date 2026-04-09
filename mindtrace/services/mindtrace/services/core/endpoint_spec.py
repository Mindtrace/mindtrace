"""Declarative endpoint specification for Service classes."""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from mindtrace.core import TaskSchema


@dataclasses.dataclass(frozen=True)
class EndpointSpec:
    """Static description of a service endpoint.

    Can be created explicitly in an ``_endpoint_specs`` list **or** implicitly
    via the :func:`endpoint` decorator.

    Example using the decorator (preferred)::

        class EchoService(Service):
            @endpoint("echo", schema=echo_task)
            def echo(self, payload: EchoInput) -> EchoOutput:
                return EchoOutput(echoed=payload.message)

    Example using a class-level list (legacy, still supported)::

        class EchoService(Service):
            _endpoint_specs = [
                EndpointSpec(path="echo", method_name="echo", schema=echo_task),
            ]
    """

    path: str
    method_name: str
    schema: TaskSchema | None = None
    methods: tuple[str, ...] = ("POST",)
    scope: str = "public"
    as_tool: bool = False
    autolog_kwargs: dict[str, Any] | None = None
    api_route_kwargs: dict[str, Any] | None = None


def endpoint(
    path: str,
    schema: TaskSchema | None = None,
    *,
    methods: tuple[str, ...] = ("POST",),
    scope: str = "public",
    as_tool: bool = False,
    autolog_kwargs: dict[str, Any] | None = None,
    api_route_kwargs: dict[str, Any] | None = None,
) -> Callable:
    """Mark a Service method as an endpoint.

    The decorated method's name is used automatically — no string
    ``method_name`` is needed.

    Example::

        class EchoService(Service):
            @endpoint("echo", schema=echo_task)
            def echo(self, payload):
                ...

            @endpoint("stream/start", methods=("GET",))
            def start_stream(self):
                ...
    """

    def decorator(func: Callable) -> Callable:
        func._endpoint_spec = EndpointSpec(
            path=path,
            method_name=func.__name__,
            schema=schema,
            methods=methods,
            scope=scope,
            as_tool=as_tool,
            autolog_kwargs=autolog_kwargs,
            api_route_kwargs=api_route_kwargs,
        )
        return func

    return decorator
