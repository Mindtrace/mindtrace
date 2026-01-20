# Mindtrace Agents

## Mindtrace Tools

### CLI Commands

#### List Toolkits and Tools

```bash
# List all toolkits
mindtrace tools list

# List tools in a specific toolkit
mindtrace tools list basler_camera_tools

# Verbose output with descriptions
mindtrace tools list basler_camera_tools --verbose
```

#### Verify a Toolkit

```bash
# Verify a built-in toolkit
mindtrace tools pull basler_camera_tools

# Pull from external package (must be installed)
mindtrace tools pull external_tools --package external-tools

# Install and pull from external package
mindtrace tools pull external_tools --package external-tools --install

# Install from GitHub and pull
mindtrace tools pull my_tools --package git+https://github.com/user/tools.git --install
```

#### Serve Tools over Remote MCP

```bash
# Serve all tools from a toolkit (name is required for registry tracking)
mindtrace tools serve basler_camera_tools --name camera-server

# Serve multiple toolkits
mindtrace tools serve basler_camera_tools my_tools --name production-server

# Serve with tag filtering
mindtrace tools serve basler_camera_tools --tags camera --name camera-tools

# Custom host and port
mindtrace tools serve basler_camera_tools --host 0.0.0.0 --port 8080 --name my-server

# Production mode with multiple workers
mindtrace tools serve basler_camera_tools --workers 4 --name production-server
```

#### List Registered Servers

```bash
# List all registered servers
mindtrace tools list-servers

# Show detailed information
mindtrace tools list-servers --verbose

# Remove stopped servers from registry
mindtrace tools list-servers --cleanup
```

#### Stop a Running Server

```bash
# Stop server by name
mindtrace tools stop --name camera-server

# Stop server on specific port
mindtrace tools stop --port 8080

# Stop server with custom host and port
mindtrace tools stop --host localhost --port 8000

# Stop using full URL
mindtrace tools stop --url http://localhost:8000
```

#### Get Information

```bash
# Get toolkit information
mindtrace tools info basler_camera_tools

# Get specific tool information
mindtrace tools info basler_camera_tools --tool discover_camera_parameters
```

### Serving Tools Programmatically

```python
from mindtrace.agents.server import create_mcp_server

# Create and run a server
server = create_mcp_server(
    toolkits=["basler_camera_tools"],
    tags={"camera"},  # Optional: filter by tags
    name="mindtrace-camera-tools",
)

server.run(host="0.0.0.0", port=8000)
```

## Using External Toolkits

You can use toolkits from external packages without modifying the mindtrace package.

### Method 1: Entry Point Registration (Recommended)

External packages can auto-register their toolkits using Python entry points:

**In the external package's `pyproject.toml`:**
```toml
[project.entry-points."mindtrace.agents.toolkits"]
external_tools = "external_tools.tools:get_toolkit_info"
```

**In the external package's code:**
```python
# external_tools/tools.py
__toolkit_name__ = "external_tools"
__toolkit_description__ = "External tools"
__toolkit_tags__ = ["external"]
__toolkit_version__ = "1.0.0"

async def my_tool():
    return {"result": "value"}

__all__ = ["my_tool"]

# Entry point function
def get_toolkit_info():
    return {
        "toolkit_name": "external_tools",
        "module_path": "external_tools.tools",
    }
```

After installing the package, the toolkit is automatically discoverable:
```bash
# List all toolkits (includes external ones)
mindtrace tools list

# Use external toolkit
mindtrace tools serve external_tools
```

### Method 2: Manual Package Specification

If a package doesn't use entry points, specify it manually:

```bash
# Pull toolkit from specific package
mindtrace tools pull my_tools --package my_package_name

# Install and pull
mindtrace tools pull my_tools --package my_package_name --install
```

## Creating New Toolkits

To add new tools to the mindtrace package, follow these steps:

### Step 1: Create a New Tool Module

Create a new file in `mindtrace/agents/tools/`, for example `my_tools.py`:

```python
"""My Custom Tools - Example toolkit."""

from typing import Any, Dict

# Toolkit metadata (required)
__toolkit_name__ = "my_tools"
__toolkit_description__ = "My custom tools for specific tasks"
__toolkit_tags__ = ["custom", "example"]
__toolkit_version__ = "1.0.0"


async def my_tool(param: str) -> Dict[str, Any]:
    """Do something useful.
    
    Args:
        param: A parameter description.
        
    Returns:
        A dictionary with the result.
        
    Example:
        >>> result = await my_tool("value")
        >>> print(result)
    """
    # Your implementation here
    return {
        "success": True,
        "result": f"Processed: {param}"
    }


# Export all tools (required)
__all__ = ["my_tool"]
```

### Step 2: Register in `__init__.py`

Edit `mindtrace/agents/tools/__init__.py`:

```python
"""Tools package for mindtrace agents."""

from mindtrace.agents.tools import basler_camera_tools, my_tools

__all__ = ["basler_camera_tools", "my_tools"]
```

### Step 3: Use Your New Toolkit

```python
# Import and use
from mindtrace.agents.tools import my_tools

result = await my_tools.my_tool("test")

# Or serve it
# mindtrace tools serve my_tools
```

## Tool Metadata

Each toolkit module should define the following metadata:

| Attribute | Description | Required |
|-----------|-------------|----------|
| `__toolkit_name__` | Name of the toolkit | No (defaults to module name) |
| `__toolkit_description__` | Description of the toolkit | No (defaults to docstring) |
| `__toolkit_tags__` | List of tags for filtering | No (defaults to empty) |
| `__toolkit_version__` | Version of the toolkit | No (defaults to "0.0.0") |
| `__all__` | List of exported tools | **Yes** |

## Best Practices

### Tool Function Design

- ✅ Use `async def` for I/O-bound operations
- ✅ Provide detailed docstrings with Args and Returns sections
- ✅ Use type hints for all parameters and return values
- ✅ Return dictionaries for complex data structures
- ✅ Handle errors gracefully with try/except

### Error Handling

```python
async def my_tool(param: str) -> Dict[str, Any]:
    """Tool with proper error handling."""
    try:
        # Your logic here
        result = await some_operation(param)
        return {"success": True, "data": result}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {e}"}
```

### Toolkit Organization

- ✅ One toolkit per domain (e.g., cameras, labeling, data processing)
- ✅ Group related tools together
- ✅ Use meaningful tags for filtering
- ✅ Keep tools focused and single-purpose

## API Reference

### ToolkitLoader

```python
from mindtrace.agents.toolkit import ToolkitLoader

loader = ToolkitLoader()

# Discover all toolkits
toolkits = loader.discover_toolkits()

# Load a specific toolkit
toolkit = loader.load_toolkit("basler_camera_tools")

# Filter tools by tags
camera_tools = toolkit.filter_by_tags({"camera"})
```

### MCPServer

```python
from mindtrace.agents.server import MCPServer

# Create a custom server
server = MCPServer(
    name="my-custom-server",
    version="1.0.0",
    description="My custom MCP server"
)

# Add toolkits with filtering
server.add_toolkit("basler_camera_tools", tags={"camera"})

# List registered tools
print(server.list_tools())

# Run the server
server.run(host="0.0.0.0", port=8000)
```

## Troubleshooting

### Import Errors

```bash
# Verify toolkit can be loaded
mindtrace tools pull basler_camera_tools

# Check if toolkit is discoverable
mindtrace tools list
```

### Server Won't Start

```bash
# Check if port is already in use
lsof -i :8000

# Try a different port
mindtrace tools serve basler_camera_tools --port 8001
```

### Tool Not Found

Ensure the tool is:
1. Defined in the toolkit module
2. Listed in `__all__`
3. A callable function (not a class or variable)

## Contributing

To add new toolkits to mindtrace:

1. Create your toolkit module in `mindtrace/agents/tools/`
2. Follow the toolkit structure and metadata guidelines
3. Add tests for your tools
4. Update `tools/__init__.py` to export your toolkit
5. Update this README with usage examples if needed


