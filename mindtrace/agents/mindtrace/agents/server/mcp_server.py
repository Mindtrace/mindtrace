"""FastMCP-based server for serving Mindtrace tools over remote MCP.

This module provides a production-grade MCP server that can serve selected
tools from toolkits with tag-based filtering.
"""

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Set

from fastmcp import FastMCP
from pydantic import Field

from mindtrace.agents.toolkit import ToolkitLoader, ToolkitMetadata


class MCPServer:
    """MCP Server for serving Mindtrace tools.
    
    This server uses FastMCP to expose tools over remote MCP with support for:
    - Multiple toolkit loading
    - Tag-based filtering
    - Automatic tool registration
    - Type-safe parameter handling
    """
    
    def __init__(
        self,
        name: str = "mindtrace-tools",
        version: str = "0.7.1",
        description: str = "Mindtrace Tools MCP Server",
        base_package: str = "mindtrace.agents.tools"
    ):
        """Initialize the MCP server.
        
        Args:
            name: The name of the MCP server.
            version: The version of the server.
            description: A description of the server.
            base_package: Base package for toolkit discovery. Change this to use
                         external toolkits (e.g., "my_custom_tools").
        """
        self.name = name
        self.version = version
        self.description = description
        self.mcp = FastMCP(name)
        self.toolkit_loader = ToolkitLoader(base_package=base_package)
        self._registered_tools: Set[str] = set()
    
    def add_toolkit(
        self,
        toolkit_name: str,
        tags: Optional[Set[str]] = None
    ) -> int:
        """Add a toolkit to the server with optional tag filtering.
        
        Args:
            toolkit_name: The name of the toolkit to add.
            tags: Optional set of tags to filter tools. If None, all tools are added.
            
        Returns:
            The number of tools added.
            
        Raises:
            ImportError: If the toolkit cannot be loaded.
        """
        toolkit = self.toolkit_loader.load_toolkit(toolkit_name)
        tools_to_add = toolkit.filter_by_tags(tags) if tags else toolkit.tools
        
        count = 0
        for tool in tools_to_add:
            if tool.name not in self._registered_tools:
                self._register_tool(tool, toolkit)
                self._registered_tools.add(tool.name)
                count += 1
        
        return count
    
    def _register_tool(self, tool: Any, toolkit: ToolkitMetadata):
        """Register a single tool with FastMCP.
        
        Args:
            tool: The tool metadata to register.
            toolkit: The toolkit metadata.
        """
        # Get the function signature
        sig = inspect.signature(tool.function)
        
        # Create a wrapper that FastMCP can use
        if tool.is_async:
            async def tool_wrapper(**kwargs):
                return await tool.function(**kwargs)
        else:
            def tool_wrapper(**kwargs):
                return tool.function(**kwargs)
        
        # Copy over the signature and docstring
        tool_wrapper.__signature__ = sig
        tool_wrapper.__doc__ = tool.description
        tool_wrapper.__name__ = tool.name
        tool_wrapper.__annotations__ = tool.function.__annotations__
        
        # Register with FastMCP
        self.mcp.tool()(tool_wrapper)
    
    def get_app(self):
        """Get the FastMCP application instance.
        
        Returns:
            The FastMCP application.
        """
        return self.mcp
    
    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        **kwargs
    ):
        """Run the MCP server.
        
        Args:
            host: The host to bind to.
            port: The port to bind to.
            **kwargs: Additional arguments to pass to uvicorn.
        """
        import uvicorn
        
        uvicorn.run(
            self.mcp,
            host=host,
            port=port,
            **kwargs
        )
    
    def list_tools(self) -> List[str]:
        """List all registered tools.
        
        Returns:
            List of registered tool names.
        """
        return sorted(self._registered_tools)


def create_mcp_server(
    toolkits: List[str],
    tags: Optional[Set[str]] = None,
    name: str = "mindtrace-tools",
    version: str = "0.7.1"
) -> MCPServer:
    """Create and configure an MCP server with specified toolkits.
    
    Args:
        toolkits: List of toolkit names to load.
        tags: Optional set of tags to filter tools.
        name: The name of the server.
        version: The version of the server.
        
    Returns:
        Configured MCPServer instance.
        
    Example:
        >>> server = create_mcp_server(
        ...     toolkits=["basler_camera_tools"],
        ...     tags={"camera"}
        ... )
        >>> server.run(host="0.0.0.0", port=8000)
    """
    server = MCPServer(name=name, version=version)
    
    for toolkit_name in toolkits:
        try:
            count = server.add_toolkit(toolkit_name, tags=tags)
            print(f"Loaded {count} tools from '{toolkit_name}'")
        except ImportError as e:
            print(f"Warning: Failed to load toolkit '{toolkit_name}': {e}")
    
    print(f"\nTotal tools registered: {len(server.list_tools())}")
    print(f"Tools: {', '.join(server.list_tools())}")
    
    return server


# Convenience function for stdio mode
def create_stdio_server(
    toolkits: List[str],
    tags: Optional[Set[str]] = None
) -> FastMCP:
    """Create an MCP server configured for stdio transport.
    
    Args:
        toolkits: List of toolkit names to load.
        tags: Optional set of tags to filter tools.
        
    Returns:
        FastMCP instance configured for stdio.
        
    Example:
        >>> server = create_stdio_server(["basler_camera_tools"])
        >>> # Use with MCP stdio transport
    """
    server = create_mcp_server(toolkits, tags=tags)
    return server.get_app()

