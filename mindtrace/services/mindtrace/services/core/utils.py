from typing import Type

import httpx
from fastapi import HTTPException

from mindtrace.services.core.connection_manager import ConnectionManager


def register_connection_manager(connection_manager: Type["ConnectionManager"]):
    """Register a connection manager for a server class.

    This decorator is used to register a connection manager for a server class. The connection manager is used to
    communicate with the server. The connection manager must be a subclass of ConnectionManager.

    Args:
        connection_manager: The connection manager class.

    Example::

        import requests
        from mindtrace.services import ConnectionManager, Service

        class MyConnectionManager(ConnectionManager):
            def __init__(self, url):
                super().__init__(url)

            def add(arg1, arg2):
                response = requests.request("POST", str(self.url) + "add", json={"arg1": arg1, "arg2": arg2})
                return json.loads(response.content)["sum"]

        @register_connection_manager(MyConnectionManager)
        class MyService(Service):
            def __init__(self):
                super().__init__()
                self.add_endpoint("add", self.add)

            def add(self, arg1, arg2):
                return {"sum": arg1 + arg2}

        cm = MyService.launch()  # Returns a MyConnectionManager instance, NOT a MyServer instance
        sum = cm.add(1, 2)  # Calls add method in MyConnectionManager

    """

    def wrapper(server_class):
        server_class._client_interface = connection_manager
        return server_class

    return wrapper


def _validate_payload(args, kwargs, input_schema, endpoint_name: str, validate_input: bool) -> dict:
    """Build the JSON payload for a generated endpoint call.

    With validation off, kwargs flow through unchanged. With validation on, either a single
    positional ``input_schema`` instance OR kwargs are accepted (not both) — any other shape
    raises ``ValueError``.
    """
    if not validate_input:
        return kwargs
    if args:
        if len(args) != 1 or not isinstance(args[0], input_schema) or kwargs:
            raise ValueError(
                f"Service method {endpoint_name} must be called with either kwargs or a single "
                f"argument of type {input_schema}"
            )
        return args[0].model_dump(mode="json")
    if input_schema is None:
        return {}
    return input_schema(**kwargs).model_dump(mode="json")


def _parse_response(response: httpx.Response, output_schema, validate_output: bool):
    """Return the parsed response, raising ``HTTPException`` on non-200; tolerates empty bodies."""
    if response.status_code != 200:
        raise HTTPException(response.status_code, response.text)
    try:
        result = response.json()
    except Exception:
        result = {"success": True}
    if not validate_output:
        return result
    return output_schema(**result) if output_schema is not None else result


def _make_endpoint_methods(endpoint_name: str, endpoint_path: str, input_schema, output_schema):
    """Build a ``(sync, async)`` method pair that POSTs to ``endpoint_path`` on ``self.url``."""

    def method(self, *args, validate_input: bool = True, validate_output: bool = True, timeout=60, **kwargs):
        payload = _validate_payload(args, kwargs, input_schema, endpoint_name, validate_input)
        res = httpx.post(str(self.url).rstrip("/") + endpoint_path, json=payload, timeout=timeout)
        return _parse_response(res, output_schema, validate_output)

    async def amethod(self, *args, validate_input: bool = True, validate_output: bool = True, timeout=60, **kwargs):
        payload = _validate_payload(args, kwargs, input_schema, endpoint_name, validate_input)
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                str(self.url).rstrip("/") + endpoint_path,
                json=payload,
                timeout=timeout,
            )
        return _parse_response(res, output_schema, validate_output)

    return method, amethod


def generate_connection_manager(
    service_cls, protected_methods: list[str] = ["shutdown", "ashutdown", "status", "astatus"]
) -> type:
    """Generates a dedicated ConnectionManager class with one method per endpoint.

    Args:
        service_cls: The service class to generate a connection manager for.
        protected_methods: A list of methods that should not be overridden by dynamic methods.

    Returns:
        A ConnectionManager class with one method per endpoint.
    """

    class_name = f"{service_cls.__name__}ConnectionManager"

    class ServiceConnectionManager(ConnectionManager):
        pass  # Methods will be added dynamically

    temp_service = service_cls(live_service=False)

    ServiceConnectionManager._service_class = service_cls
    ServiceConnectionManager._service_endpoints = temp_service._endpoints

    for endpoint_name, endpoint in temp_service._endpoints.items():
        if endpoint_name in protected_methods:
            continue

        endpoint_path = f"/{endpoint_name}"
        method, amethod = _make_endpoint_methods(
            endpoint_name, endpoint_path, endpoint.input_schema, endpoint.output_schema
        )

        method_name = endpoint_name.replace(".", "_")
        method.__name__ = method_name
        method.__doc__ = f"Calls the `{endpoint_name}` pipeline at `{endpoint_path}`"
        setattr(ServiceConnectionManager, method_name, method)

        async_method_name = f"a{method_name}"
        amethod.__name__ = async_method_name
        amethod.__doc__ = f"Async version: Calls the `{endpoint_name}` pipeline at `{endpoint_path}`"
        setattr(ServiceConnectionManager, async_method_name, amethod)

    ServiceConnectionManager.__name__ = class_name
    return ServiceConnectionManager
