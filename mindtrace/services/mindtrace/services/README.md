# Mindtrace Services

The `mindtrace-services` module provides the core microservice framework for the Mindtrace ecosystem. It enables rapid development, deployment, and management of distributed services with robust and auto generated connection management, and comprehensive testing support.

## Purpose

- **Service Class**: Unified base for all Mindtrace microservices, inspired by the ServerBase component from the mtrix package (now renamed to `Service`).
- **Auto-Generated Connection Managers**: Connect to services with auto-generated client interfaces.
- **Endpoint Management**: Strongly-typed, schema-driven endpoint registration and validation.
- **Stress Testing**: Built-in support for stress, integration, and unit testing.

## Installation

```bash
uv add mindtrace-services
```

## Architecture

- **Service (`Service`)**: Base class for all services, providing endpoint registration, FastAPI integration, and lifecycle management.
- **ConnectionManager**: Client-side helper for communicating with any Mindtrace service. Auto-generated if not explicitly registered.
- **Endpoint Schemas**: All endpoints require a `TaskSchema` for input/output validation.
- **Launcher**: Gunicorn-based launcher for production deployment.

## Auto-generation for Connection Managers

When calling a service's `connect` method, the following logic is used:

```python
if cls._client_interface is None:
    return generate_connection_manager(cls)(url=url)
else:
    return cls._client_interface(url=url)
```

- If a `ConnectionManager` is not explicitly registered, one is auto-generated for the service, exposing all endpoints as methods.
- If a `ConnectionManager` is registered, it is used as before.

### Updated `add_endpoint` Method

- `Service.add_endpoint()` now requires a `schema: TaskSchema`, which is stored in the service's `endpoints` dictionary.
- The auto-generator uses these schemas to add type validation and define the returned ConnectionManager's methods with the correct arguments.
- All endpoints (except `shutdown`) are exposed as methods on the connection manager.

### Both `GET` and `POST` Requests Default to Connection Manager Methods

All generated endpoints are now methods in the returned connection manager. Naked properties are not currently supported:

```python
from mindtrace.services import Service
cm = Service.launch()
cm.status  # no longer supported
cm.status()  # now generated as a method
```

## Usage Example

See [`sample/echo_service.py`](./sample/echo_service.py) for a full example. Basic usage:

```python
from mindtrace.services import Service

cm = Service.launch()

cm.status()      # StatusOutput(status=<ServerStatus.Available: 'Available'>)
cm.heartbeat()   # HeartbeatOutput(...)
cm.endpoints()   # EndpointsOutput(endpoints=[...])
cm.server_id()   # ServerIDOutput(...)
cm.pid_file()    # PIDFileOutput(...)
cm.shutdown(block=True)  # ShutdownOutput(shutdown=True)
```

### Defining a Custom Service

```python
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
```

## Testing & Coverage

The test runner supports unit, integration, and stress tests:

```bash
# Run all test suites
ds test

# Run specific suites
ds test --unit --stress
```

- Test suites are run individually, but coverage is appended for later suites.
- The stress test suite provides verbose output (e.g., tqdm progress bars).
- Example suite times:

```
unit:        522 passed, 5 skipped in 4.56s
unit+torch:  527 passed in 9.69s
integration: 58 passed in 41.78s
stress:      7 passed in 208.89s (0:03:28)
```

- All test suites should pass, with `ds test --unit` yielding ~97% coverage, and `ds test --unit --integration` yielding 100%.

## API Reference

### Service
- Base class for all Mindtrace services. Provides endpoint registration, FastAPI app, and lifecycle management.

### ConnectionManager
- Client-side helper for communicating with Mindtrace services. Auto-generated if not registered.

### generate_connection_manager
- Dynamically creates a ConnectionManager for a given Service, exposing all endpoints as methods.

### add_endpoint
- Register a new endpoint with a schema for input/output validation.

### TaskSchema
- Used to define input/output types for endpoints.

## MCP Integration: Exposing Service Endpoints as Tools

### What is MCP?
The Model Context Protocol (MCP) is a protocol for exposing service functionality as callable tools, enabling both programmatic and interactive access to service endpoints. MCP allows you to interact with your microservices not only via HTTP endpoints but also as tools that can be listed and invoked through a unified client interface.

### How MCP is Integrated
- **FastMCP SDK is used to create a MCP compliant server:**
  [FastMCP](https://gofastmcp.com/getting-started/welcome) automatically handles a standard Python function to be used as a tool:
    - Tool Name: It uses the function name (add) as the tool’s name.
    - Description: It uses the function’s docstring as the tool’s description for the LLM.
    - Schema: It inspects the type hints (a: int, b: int) to generate a JSON schema for the inputs.
- **Mounting MCP on FastAPI:**
  Each `Service` instance mounts an MCP server on the FastAPI app at `/mcp-server/mcp/`. This allows the same service to be accessed both via REST endpoints and as MCP tools.
- **Exposing Endpoints as Tools:**
  When adding an endpoint using `add_endpoint`, you can set `as_tool=True` to expose that endpoint as an MCP tool:
  ```python
  self.add_endpoint("echo", self.echo, schema=echo_task, as_tool=True)
  ```
  This makes the `echo` function available both as a REST endpoint and as an MCP tool.

### Example: EchoService with MCP
See [`sample/echo_mcp.py`](./sample/echo_mcp.py):
```python
from mindtrace.services.sample.echo_mcp import EchoService

# Launch the service
connection_manager = EchoService.launch(port=8080, host="localhost", wait_for_launch=True, timeout=30)
mcp_url = str(connection_manager.url) + 'mcp-server/mcp/'

# Synchronous call via connection manager
result = connection_manager.echo(message="Hello, World!")
print(result.echoed)
```

### Adding Tools Directly with `add_tool`
In addition to exposing same class methods as endpoints and tools, you can register standalone functions as MCP tools using `self.add_tool`. These tools will be available via the MCP interface but not as HTTP endpoints.

Example:
```python
# Define a tool function
def reverse_message(payload: EchoInput) -> EchoOutput:
    """A demo tool that reverses the input message."""
    reversed_msg = payload.message[::-1]
    return EchoOutput(echoed=reversed_msg)

class EchoService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_task, as_tool=True)
        # Register the reverse_message tool directly
        self.add_tool("reverse_message", reverse_message)
```

Now, both `echo` and `reverse_message` are available as MCP tools.

#### Using the MCP Client (with custom tool)
You can call both the standard and custom tools from the client:

```python
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import asyncio

async def mcp_example():
    async with streamablehttp_client(mcp_url) as (read, write, session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Available tools:", [tool.name for tool in tools.tools])
            # Call the 'echo' tool
            result = await session.call_tool("echo", {"payload": {"message": "Alice"}})
            print("Echo tool response:", result)
            # Call the 'reverse_message' tool
            result = await session.call_tool("reverse_message", {"payload": {"message": "Alice"}})
            print("Reverse tool response:", result)

asyncio.run(mcp_example())
```

### Key Points
- Endpoints added with `as_tool=True` are available as both HTTP endpoints and MCP tools.
- The sample EchoService demonstrates both REST and MCP tool usage.
- The MCP client allows you to list and call tools programmatically.

For trial purposes, see the sample files:
- [`sample/echo_mcp.py`](./sample/echo_mcp.py)
- [`samples/services/echo_mcp_service.py`](../../samples/services/echo_mcp_service.py)
