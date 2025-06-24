from typing import Optional, Type, TYPE_CHECKING

import httpx
from fastapi import HTTPException

if TYPE_CHECKING:
    from mindtrace.services import ServerBase
from mindtrace.core import Mindtrace
from mindtrace.services.base.connection_manager import ConnectionManager


def add_endpoint(app, path, self: Optional["ServerBase"], **kwargs):
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
    communicate with the server. The connection manager must be a subclass of ConnectionManagerBase.

    Args:
        connection_manager: The connection manager class.

    Example::

        import requests
        from mindtrace.services import ConnectionManagerBase, ServerBase

        class MyConnectionManager(ConnectionManagerBase):
            def __init__(self, url):
                super().__init__(url)

            def add(arg1, arg2):
                response = requests.request("POST", str(self.url) + "add", json={"arg1": arg1, "arg2": arg2})
                return json.loads(response.content)["sum"]

        @register_connection_manager(MyConnectionManager)
        class MyServer(ServerBase):
            def __init__(self):
                super().__init__()
                self.add_endpoint("add", self.add)

            def add(self, arg1, arg2):
                return {"sum": arg1 + arg2}

        cm = MyServer.launch()  # Returns a MyConnectionManager instance, NOT a MyServer instance
        sum = cm.add(1, 2)  # Calls add method in MyConnectionManager

    """

    def wrapper(server_class):
        server_class._client_interface = connection_manager
        return server_class

    return wrapper


def generate_connection_manager(service_cls):
    """Generates a dedicated ConnectionManager class with one method per endpoint."""

    class_name = f"{service_cls.__name__}ConnectionManager"

    class ServiceConnectionManager(ConnectionManager):
        pass  # Methods will be added dynamically

    # Create a temporary service instance to get the endpoints
    temp_service = service_cls()
    
    # Properties that should not be overridden by dynamic methods
    protected_methods = ['shutdown']
    
    # Dynamically define one method per endpoint
    for endpoint_name, endpoint in temp_service._endpoints.items():
        # Skip if this would override an existing method in ConnectionManager
        if endpoint_name in protected_methods:
            continue
            
        endpoint_path = f"/{endpoint_name}"

        def make_method(endpoint_path, input_schema, output_schema):
            def method(self, blocking: bool = True, **kwargs):
                payload = input_schema(**kwargs).dict() if input_schema is not None else {}
                res = httpx.post(
                    str(self.url).rstrip('/') + endpoint_path,
                    json=payload,
                    params={"blocking": str(blocking).lower()},
                    timeout=30
                )
                if res.status_code != 200:
                    raise HTTPException(res.status_code, res.text)
                
                # Handle empty responses (e.g., from shutdown endpoint)
                try:
                    result = res.json()
                except:
                    result = {"success": True}  # Default response for empty content
                    
                if not blocking:
                    return result  # raw job result dict
                return output_schema(**result) if output_schema is not None else result
            
            async def amethod(self, blocking: bool = True, **kwargs):
                payload = input_schema(**kwargs).dict() if input_schema is not None else {}
                async with httpx.AsyncClient(timeout=30) as client:
                    res = await client.post(
                        str(self.url).rstrip('/') + endpoint_path,
                        json=payload,
                        params={"blocking": str(blocking).lower()}
                    )
                if res.status_code != 200:
                    raise HTTPException(res.status_code, res.text)
                
                # Handle empty responses (e.g., from shutdown endpoint)
                try:
                    result = res.json()
                except:
                    result = {"success": True}  # Default response for empty content
                    
                if not blocking:
                    return result  # raw job result dict
                return output_schema(**result) if output_schema is not None else result
            
            return method, amethod

        method, amethod = make_method(endpoint_path, endpoint.input_schema, endpoint.output_schema)
        
        # Set up sync method
        method.__name__ = endpoint_name
        method.__doc__ = f"Calls the `{endpoint_name}` pipeline at `{endpoint_path}`"
        setattr(ServiceConnectionManager, endpoint_name, method)
        
        # Set up async method
        amethod.__name__ = f"a{endpoint_name}"
        amethod.__doc__ = f"Async version: Calls the `{endpoint_name}` pipeline at `{endpoint_path}`"
        setattr(ServiceConnectionManager, f"a{endpoint_name}", amethod)

    def get_job(self, job_id: str):
        res = httpx.get(str(self.url).rstrip('/') + f"/job/{job_id}", timeout=10)
        if res.status_code == 404:
            return None
        elif res.status_code != 200:
            raise HTTPException(res.status_code, res.text)
        return res.json()
    
    async def aget_job(self, job_id: str):
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(str(self.url).rstrip('/') + f"/job/{job_id}")
        if res.status_code == 404:
            return None
        elif res.status_code != 200:
            raise HTTPException(res.status_code, res.text)
        return res.json()
    
    setattr(ServiceConnectionManager, "get_job", get_job)
    setattr(ServiceConnectionManager, "aget_job", aget_job)

    ServiceConnectionManager.__name__ = class_name
    return ServiceConnectionManager