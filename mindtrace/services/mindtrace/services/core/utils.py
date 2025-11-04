from typing import TYPE_CHECKING, Optional, Type

import httpx
from fastapi import HTTPException

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.services import Service
from mindtrace.core import Mindtrace
from mindtrace.services.core.connection_manager import ConnectionManager


def add_endpoint(app, path, self: Optional["Service"], **kwargs):
    """Register a new endpoint.

    This decorator method is functionally identical as calling add_endpoint on a Service instance. It is useful when
    the endpoints are defined in a separate method, such as grouping api routes in a more complicated FastAPI app.

    Args:
        app: The FastAPI app.
        path: The endpoint path.
        self: The server instance.
        **kwargs: Additional arguments to pass when creating the FastAPI route.

    Example::

        from fastapi import FastAPI
        from mindtrace.services import Service

        class MyServer(Service):
            def __init__(self):
                super().__init__()

                self.add_endpoint(path="/status_using_method", func=self.status)
                self.create_app()

            def status(self):
                return {"status": "Available"}

            def create_app():
                # May put all the endpoints in a single method, and call the method in __init__.

                @add_endpoint(self.app, "/status_using_decorator", self=self)
                def status():
                    return {"status": "Available"}

                @add_endpoint(self.app, "/another_hundred_endpoints", self=self)
                def another_hundred_endpoints():
                    return


    """
    self._endpoints.append(path.removeprefix("/"))

    def wrapper(func):
        app.add_api_route(f"/{path}", endpoint=Mindtrace.autolog(self=self)(func), methods=["POST"], **kwargs)

    return wrapper


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

    # Create a temporary service instance to get the endpoints
    temp_service = service_cls(live_service=False)

    # Store service class and endpoints
    ServiceConnectionManager._service_class = service_cls
    ServiceConnectionManager._service_endpoints = temp_service._endpoints

    # Dynamically define one method per endpoint
    for endpoint_name, endpoint in temp_service._endpoints.items():
        # Skip if this would override an existing method in ConnectionManager
        if endpoint_name in protected_methods:
            continue

        endpoint_path = f"/{endpoint_name}"

        def make_method(endpoint_path, input_schema, output_schema):
            def method(self, *args, validate_input: bool = True, validate_output: bool = True, **kwargs):
                if validate_input:
                    if args:
                        if len(args) != 1:
                            raise ValueError(
                                f"Service method {endpoint_name} must be called with either kwargs or a single argument of type {input_schema}"
                            )
                        if not isinstance(args[0], input_schema):
                            raise ValueError(
                                f"Service method {endpoint_name} must be called with either kwargs or a single argument of type {input_schema}"
                            )
                        if kwargs:
                            raise ValueError(
                                f"Service method {endpoint_name} must be called with either kwargs or a single argument of type {input_schema}"
                            )
                        payload = args[0].model_dump()
                    else:
                        payload = input_schema(**kwargs).model_dump() if input_schema is not None else {}
                else:
                    payload = kwargs
                res = httpx.post(str(self.url).rstrip("/") + endpoint_path, json=payload, timeout=60)
                if res.status_code != 200:
                    raise HTTPException(res.status_code, res.text)

                # Handle empty responses (e.g., from shutdown endpoint)
                try:
                    result = res.json()
                except Exception:
                    result = {"success": True}  # Default response for empty content

                if not validate_output:
                    return result  # raw result dict
                return output_schema(**result) if output_schema is not None else result

            async def amethod(self, *args, validate_input: bool = True, validate_output: bool = True, **kwargs):
                if validate_input:
                    if args:
                        if len(args) != 1:
                            raise ValueError(
                                f"Service method a{endpoint_name} must be called with either kwargs or a single argument of type {input_schema}"
                            )
                        if not isinstance(args[0], input_schema):
                            raise ValueError(
                                f"Service method a{endpoint_name} must be called with either kwargs or a single argument of type {input_schema}"
                            )
                        if kwargs:
                            raise ValueError(
                                f"Service method a{endpoint_name} must be called with either kwargs or a single argument of type {input_schema}"
                            )
                        payload = args[0].model_dump()
                    else:
                        payload = input_schema(**kwargs).model_dump() if input_schema is not None else {}
                else:
                    payload = kwargs
                async with httpx.AsyncClient(timeout=60) as client:
                    res = await client.post(str(self.url).rstrip("/") + endpoint_path, json=payload, timeout=60)
                if res.status_code != 200:
                    raise HTTPException(res.status_code, res.text)

                # Handle empty responses (e.g., from shutdown endpoint)
                try:
                    result = res.json()
                except Exception:
                    result = {"success": True}  # Default response for empty content

                if not validate_output:
                    return result  # raw result dict
                return output_schema(**result) if output_schema is not None else result

            return method, amethod

        method, amethod = make_method(endpoint_path, endpoint.input_schema, endpoint.output_schema)

        # Replace dots with underscores to make it a valid identifier
        method_name = endpoint_name.replace(".", "_")

        # Set up sync method
        method.__name__ = method_name
        method.__doc__ = f"Calls the `{endpoint_name}` pipeline at `{endpoint_path}`"
        setattr(ServiceConnectionManager, method_name, method)

        # Set up async method
        async_method_name = f"a{method_name}"
        amethod.__name__ = async_method_name
        amethod.__doc__ = f"Async version: Calls the `{endpoint_name}` pipeline at `{endpoint_path}`"
        setattr(ServiceConnectionManager, async_method_name, amethod)

    ServiceConnectionManager.__name__ = class_name
    return ServiceConnectionManager
