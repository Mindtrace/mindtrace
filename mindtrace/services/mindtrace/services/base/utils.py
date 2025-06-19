from typing import Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from mindtrace.services import ConnectionManagerBase, ServerBase
from mindtrace import Mindtrace


def add_endpoint(app, path, self: Optional["ServerBase"], **kwargs):
    """Register a new endpoint.

    This decorator method is functionally identical as calling add_endpoint on a ServerBase instance. It is useful when
    the endpoints are defined in a separate method, such as grouping api routes in a more complicated FastAPI app.

    Args:
        app: The FastAPI app.
        path: The endpoint path.
        self: The server instance.
        **kwargs: Additional arguments to pass when creating the FastAPI route.

    Example::

        from fastapi import FastAPI
        from mindtrace.services import ServerBase

        class MyServer(ServerBase):
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


def register_connection_manager(connection_manager: Type["ConnectionManagerBase"]):
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