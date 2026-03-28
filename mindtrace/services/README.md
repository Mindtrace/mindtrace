[![PyPI version](https://img.shields.io/pypi/v/mindtrace-services)](https://pypi.org/project/mindtrace-services/)
[![License](https://img.shields.io/pypi/l/mindtrace-services)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/services/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-services)](https://pepy.tech/projects/mindtrace-services)

# Mindtrace Services

`mindtrace-services` is Mindtrace’s typed microservice framework. Define a `Service` once with `TaskSchema` endpoint contracts, then launch it as a process, connect to it through an auto-generated client, and optionally expose those endpoints as MCP tools.

## What this package provides

- **Typed service definition** with `Service` + `TaskSchema`
- **FastAPI-backed HTTP services** with standard lifecycle endpoints
- **Auto-generated clients** via `ConnectionManager` generation
- **Built-in launch/connect workflow** for local service processes
- **First-class MCP support** through FastMCP
- **Service composition utilities** such as `Gateway` and proxy connection managers
- **Concrete integrations** such as Discord service wrappers and sample services

## Core concepts

### `Service`

`Service` is the server-side abstraction. A service instance:

- builds a FastAPI app
- tracks registered endpoints and their schemas
- mounts an MCP server
- provides standard lifecycle endpoints
- can be launched in a separate process with `Service.launch()`

### `TaskSchema`

`TaskSchema` is the typed contract for an endpoint. It defines:

- the endpoint name
- the input schema
- the output schema

That same schema is reused across the package for:

- FastAPI request validation
- generated connection manager methods
- output parsing on the client side
- MCP tool exposure

### `ConnectionManager`

`ConnectionManager` is the client-side abstraction for talking to a running service over HTTP. It provides common lifecycle methods such as:

- `status()` / `astatus()`
- `shutdown()` / `ashutdown()`
- `mcp_client` for talking to the same service via MCP

### Auto-generated connection managers

If a service does not register a custom client class, Mindtrace generates one automatically from the service’s registered endpoint schemas. Each endpoint becomes:

- a synchronous client method
- an asynchronous client method prefixed with `a`

For example, an `echo` endpoint becomes:

- `cm.echo(...)`
- `await cm.aecho(...)`

### MCP integration

Each service mounts a FastMCP app alongside its HTTP routes. Endpoints can be exposed as tools with `as_tool=True`, and services can also register MCP-only tools with `add_tool()`.

### Launcher

`Service.launch()` starts a real service process via `mindtrace.services.core.launcher`.

- On Linux/macOS this uses **Gunicorn + Uvicorn workers**
- On Windows this uses **Uvicorn directly**

This means `launch()` is process-oriented, not just an in-memory constructor.

## Service lifecycle

The usual flow is:

1. Define Pydantic input/output models
2. Wrap them in a `TaskSchema`
3. Subclass `Service`
4. Register endpoints with `add_endpoint()`
5. Launch the service with `MyService.launch()`
6. Receive a connected `ConnectionManager`
7. Call service methods as normal Python methods

## Quick start

### Define and launch a service

```python
import time

from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class EchoInput(BaseModel):
    message: str
    delay: float = 0.0


class EchoOutput(BaseModel):
    echoed: str


echo_task = TaskSchema(
    name="echo",
    input_schema=EchoInput,
    output_schema=EchoOutput,
)


class EchoService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_task)

    def echo(self, payload: EchoInput) -> EchoOutput:
        if payload.delay > 0:
            time.sleep(payload.delay)
        return EchoOutput(echoed=payload.message)


cm = EchoService.launch(wait_for_launch=True)
print(cm.status())
print(cm.echo(message="Hello"))
cm.shutdown()
```

## Built-in endpoints

Every `Service` automatically registers a standard set of lifecycle and introspection endpoints:

- `endpoints` — list registered endpoint names
- `status` — current service status
- `heartbeat` — structured health/liveness payload
- `server_id` — unique server ID
- `pid_file` — PID file path for the launched process
- `shutdown` — stop the running service

These endpoints are available over HTTP, and some are also exposed as MCP tools.

## Defining endpoints

Register endpoints with `add_endpoint()`:

```python
self.add_endpoint(
    path="echo",
    func=self.echo,
    schema=echo_task,
    as_tool=True,
)
```

Important behavior:

- routes are registered as **POST** endpoints by default
- the endpoint schema is stored in the service for later client generation
- the function is wrapped with service logging/instrumentation
- setting `as_tool=True` exposes the same function as an MCP tool

## Client generation details

If no custom connection manager is registered, `generate_connection_manager()` creates one dynamically from the service definition.

For each registered endpoint:

- a sync method is generated
- an async method is generated
- input kwargs are validated against the endpoint input schema
- HTTP responses are parsed into the endpoint output schema

### Method naming

- endpoint `echo` → `echo()` and `aecho()`
- dotted endpoint names are converted to valid Python method names by replacing `.` with `_`

### Validation controls

Generated methods support:

- `validate_input=True`
- `validate_output=True`

These can be disabled when raw payload handling is needed.

### When to write a custom connection manager

A custom connection manager is worth using when you want:

- richer convenience methods than one-method-per-endpoint
- custom retry or caching behavior
- special authentication flows
- a more domain-specific client surface

Otherwise, the generated client is usually enough.

## Launching and connecting

### `launch()`

`Service.launch()`:

- resolves the target URL
- checks that no service is already running there
- spawns a subprocess launcher
- optionally waits for the service to become reachable
- returns a connection manager when `wait_for_launch=True`

Common arguments:

- `url` — explicit full service URL
- `host` / `port` — host and port override
- `wait_for_launch` — wait until the service is available
- `timeout` — startup timeout in seconds
- `block` — keep the calling process blocked while the service runs
- `num_workers` — worker count for the launched service

### `connect()`

`Service.connect()` attaches to an already-running service and returns the appropriate connection manager.

## URL and configuration behavior

Service URLs are resolved with the following priority:

1. explicit `url`
2. explicit `host` / `port`
3. configured default URL for that service type

MCP paths are also configuration-driven. Services derive:

- the MCP mount path
- the MCP HTTP app path

from `MINDTRACE_MCP` config values.

## MCP integration

Every service creates and mounts a FastMCP app.

### Expose an endpoint as a tool

```python
self.add_endpoint("echo", self.echo, schema=echo_task, as_tool=True)
```

This makes the same function available:

- as an HTTP endpoint
- as an MCP tool

### Register an MCP-only tool

```python
def reverse_message(payload: EchoInput) -> EchoOutput:
    """Reverse the input message."""
    return EchoOutput(echoed=payload.message[::-1])


self.add_tool("reverse_message", reverse_message)
```

### MCP client access

You can connect to a service over MCP in three common ways.

#### Class-level connect

```python
client = EchoService.mcp.connect("http://localhost:8080")
```

#### Class-level launch

```python
client = EchoService.mcp.launch(host="localhost", port=8080, wait_for_launch=True)
```

#### From an existing connection manager

```python
cm = EchoService.launch(host="localhost", port=8080, wait_for_launch=True)
client = cm.mcp_client
```

## Gateway and proxy routing

The package includes service-composition helpers.

### `Gateway`

`Gateway` is a service that can register downstream FastAPI apps and forward requests to them.

It supports:

- dynamic app registration
- HTTP request forwarding
- enhanced connection behavior for registered apps

### `ProxyConnectionManager`

`ProxyConnectionManager` routes endpoint calls through a gateway instead of calling a service directly. It uses service endpoint metadata to create proxy methods matching the downstream service surface.

This is useful when a service needs to be accessed indirectly through a central gateway.

## Package layout

Key modules in this package include:

- `mindtrace.services.core.service` — base `Service` implementation
- `mindtrace.services.core.connection_manager` — base client abstraction
- `mindtrace.services.core.utils` — connection manager generation helpers
- `mindtrace.services.core.launcher` — subprocess launcher
- `mindtrace.services.core.mcp_client_manager` — MCP client helper
- `mindtrace.services.gateway.*` — gateway and proxy support
- `mindtrace.services.discord.*` — Discord integration
- `mindtrace.services.samples.*` — sample services

## Examples in this package

See the sample implementations in this package for end-to-end reference:

- `mindtrace/services/mindtrace/services/samples/echo_service.py`
- `mindtrace/services/mindtrace/services/samples/echo_mcp.py`
- `mindtrace/services/mindtrace/services/discord/README.md`

## Testing

Typical local test commands:

```bash
# Run unit tests
# (preferred default local path)
ds test --unit
```

Depending on your workflow, broader suites may also be available.

## Practical notes and caveats

- Generated endpoint methods use **POST** requests.
- Protected client methods such as `status` and `shutdown` are not overwritten by generated endpoint methods.
- A lightweight service instance may be created during client generation in order to inspect registered endpoints.
- Endpoint names should be chosen with both route readability and Python client naming in mind.
- `launch()` manages subprocesses and PID files, so it should be treated as a service runtime tool, not just object instantiation.

## Minimal MCP example

```python
import asyncio

from mindtrace.services.samples.echo_mcp import EchoService


async def main():
    client = EchoService.mcp.launch(
        host="localhost",
        port=8080,
        wait_for_launch=True,
        timeout=30,
    )
    async with client:
        tools = await client.list_tools()
        print([tool.name for tool in tools])
        result = await client.call_tool("echo", {"payload": {"message": "Hello"}})
        print(result)


asyncio.run(main())
```

## Remote MCP usage

Any Mindtrace service exposing MCP tools can also be used from MCP-capable clients such as Cursor by pointing the client at the service’s mounted MCP endpoint.

Example configuration:

```json
{
  "mcpServers": {
    "mindtrace_echo": {
      "url": "http://localhost:8080/mcp-server/mcp/"
    }
  }
}
```

Once configured, the client can list and invoke tools exposed by the service.
