import httpx
from fastapi import HTTPException
from urllib3.util.url import Url

from mindtrace.services.core.connection_manager import ConnectionManager


def build_mcp_url(base_url: str | Url, mount_path: str, http_app_path: str) -> str:
    """Build the full MCP endpoint URL from a base service URL and MCP path components.

    Args:
        base_url: The base URL of the service (e.g. "http://localhost:8080/").
        mount_path: The MCP mount path (e.g. "/mcp-server").
        http_app_path: The MCP HTTP app path (e.g. "/mcp").

    Returns:
        The full MCP URL (e.g. "http://localhost:8080/mcp-server/mcp").
    """
    base = str(base_url).rstrip("/")
    mount = mount_path.strip("/")
    app = http_app_path.strip("/")
    return f"{base}/{mount}/{app}"


def _validate_payload(args, kwargs, input_schema, endpoint_name: str, validate_input: bool) -> dict:
    """Validate input and return the payload dict for an endpoint call."""
    if not validate_input:
        return kwargs
    if args:
        if len(args) != 1 or not isinstance(args[0], input_schema):
            raise ValueError(
                f"Endpoint '{endpoint_name}' must be called with either kwargs or a single "
                f"argument of type {input_schema}"
            )
        if kwargs:
            raise ValueError(
                f"Endpoint '{endpoint_name}' must be called with either kwargs or a single "
                f"argument of type {input_schema}"
            )
        return args[0].model_dump()
    return input_schema(**kwargs).model_dump() if input_schema is not None else {}


def _parse_response(response: httpx.Response, output_schema, validate_output: bool):
    """Parse an HTTP response, optionally validating against an output schema."""
    if response.status_code != 200:
        raise HTTPException(response.status_code, response.text)
    try:
        result = response.json()
    except Exception:
        result = {"success": True}
    if not validate_output:
        return result
    return output_schema(**result) if output_schema is not None else result


def make_endpoint_methods(endpoint_name: str, endpoint_path: str, input_schema, output_schema):
    """Create a (sync, async) method pair for calling a remote endpoint.

    The returned methods expect ``self`` to have a ``url`` attribute (e.g. a
    :class:`ConnectionManager` instance). They support positional args (a single
    model instance) and kwargs with ``validate_input``/``validate_output`` flags.
    """

    def method(self, *args, validate_input: bool = True, validate_output: bool = True, **kwargs):
        payload = _validate_payload(args, kwargs, input_schema, endpoint_name, validate_input)
        res = httpx.post(str(self.url).rstrip("/") + endpoint_path, json=payload, timeout=60)
        return _parse_response(res, output_schema, validate_output)

    async def amethod(self, *args, validate_input: bool = True, validate_output: bool = True, **kwargs):
        payload = _validate_payload(args, kwargs, input_schema, endpoint_name, validate_input)
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(str(self.url).rstrip("/") + endpoint_path, json=payload, timeout=60)
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

    # Read endpoint schemas from class-level specs (no instance needed).
    class_endpoints = getattr(service_cls, "__endpoints__", {})
    endpoints_schemas = {path: spec.schema for path, spec in class_endpoints.items()}

    # Store service class and endpoints
    ServiceConnectionManager._service_class = service_cls
    ServiceConnectionManager._service_endpoints = endpoints_schemas

    # Dynamically define one method per endpoint
    for endpoint_name, endpoint in endpoints_schemas.items():
        # Skip if this would override an existing method in ConnectionManager
        if endpoint_name in protected_methods:
            continue

        endpoint_path = f"/{endpoint_name}"
        method, amethod = make_endpoint_methods(
            endpoint_name, endpoint_path, endpoint.input_schema, endpoint.output_schema
        )

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
