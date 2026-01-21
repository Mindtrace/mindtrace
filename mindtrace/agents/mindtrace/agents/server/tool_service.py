from pathlib import Path
from typing import List, Optional, Set

from mindtrace.agents.toolkit import ToolkitLoader
from mindtrace.services import Service


class ToolService(Service):
    """Service that loads and serves toolkits via MCP over HTTP.
    
    Extends Service to provide full infrastructure support:
    - Gunicorn/Uvicorn with multiple workers
    - Structured logging to files
    - PID tracking and management
    - Graceful shutdown handling
    - Status and heartbeat endpoints
    - Background launch capability
    
    Example:
        >>> # Launch in foreground with blocking
        >>> ToolService.launch(
        ...     toolkits=["basler_camera_tools"],
        ...     tags={"camera"},
        ...     host="0.0.0.0",
        ...     port=8000,
        ...     num_workers=4,
        ...     block=True
        ... )
        
        >>> # Launch in background and get connection manager
        >>> connection = ToolService.launch(
        ...     toolkits=["basler_camera_tools"],
        ...     host="localhost",
        ...     port=8000,
        ...     wait_for_launch=True
        ... )
        >>> # Server running, use connection to interact
        >>> connection.shutdown()  # Stop the server
    """
    
    def __init__(
        self, 
        toolkits: Optional[List[str]] = None,
        tags: Optional[Set[str]] = None,
        use_structlog: bool = True,
        server_name: Optional[str] = None,
        **kwargs
    ):
        """Initialize the ToolService with toolkit loading.
        
        Args:
            toolkits: List of toolkit names to load (e.g., ["basler_camera_tools"])
            tags: Optional set of tags to filter tools (e.g., {"camera", "hardware"})
            use_structlog: Whether to use structured logging (default: True)
            server_name: Optional name for this server instance (used for unique logging)
            **kwargs: Additional parameters passed to Service.__init__
                     (url, host, port, summary, description, etc.)
        """
        # Handle default values
        toolkits = toolkits or []
        
        # Convert tags to Set if it's a list (from JSON deserialization)
        if tags is not None and not isinstance(tags, set):
            tags = set(tags) if isinstance(tags, (list, tuple)) else {tags}
        
        # Store server_name before calling super().__init__
        self._server_name = server_name
        
        # Add use_structlog to kwargs to pass to parent Mindtrace class
        kwargs["use_structlog"] = use_structlog
        
        # Check if this is a live service or just for introspection
        live_service = kwargs.get('live_service', True)
        
        # Build a descriptive name
        toolkit_names = ", ".join(toolkits) if toolkits else "no toolkits"
        description = kwargs.pop("description", None)
        if description is None:
            description = f"Tool server serving: {toolkit_names}"
        
        # Initialize Service first
        super().__init__(
            description=description,
            summary=f"MCP server for {len(toolkits)} toolkit(s)",
            **kwargs
        )
        
        # Override logger with unique name per server instance
        # This ensures each server instance logs to its own file
        from mindtrace.core.logging.logger import get_logger
        
        # Create unique logger name based on server_id or server_name
        if server_name:
            unique_logger_name = f"mindtrace.agents.server.tool_service.ToolService.{server_name}"
        else:
            # Use server_id to make it unique
            unique_logger_name = f"mindtrace.agents.server.tool_service.ToolService.{self.id}"
        
        # Set up unique logger for this instance
        self.logger = get_logger(
            unique_logger_name,
            use_structlog=use_structlog,
            structlog_bind={"tool_service_name":  server_name if server_name else self.id},
            )
        
        # Store configuration
        self.toolkits = toolkits
        self.tags = tags
        self.toolkit_loader = ToolkitLoader()
        
        # Load and register toolkits only if this is a live service
        # (skip when instantiating for connection manager introspection)
        if toolkits and live_service:
            self._load_toolkits()
    
    def _load_toolkits(self):
        """Load toolkits and register their tools with the MCP server."""
        total_tools = 0
        failed_toolkits = []
        
        for toolkit_name in self.toolkits:
            try:
                # Load the toolkit
                toolkit = self.toolkit_loader.load_toolkit(toolkit_name)
                
                # Filter by tags if specified
                tools = toolkit.filter_by_tags(self.tags) if self.tags else toolkit.tools
                
                # Register each tool with the MCP server
                for tool in tools:
                    self.add_tool(tool.name, tool.function)
                    total_tools += 1
                
                self.logger.info(
                    f"Loaded {len(tools)} tools from toolkit '{toolkit_name}' "
                    f"(filtered by tags: {self.tags})" if self.tags 
                    else f"Loaded {len(tools)} tools from toolkit '{toolkit_name}'"
                )
                
            except ImportError as e:
                self.logger.warning(f"Failed to load toolkit '{toolkit_name}': {e}")
                failed_toolkits.append(toolkit_name)
            except Exception as e:
                self.logger.error(f"Error loading toolkit '{toolkit_name}': {e}")
                failed_toolkits.append(toolkit_name)
        
        # Log summary
        if total_tools > 0:
            self.logger.info(f"Successfully registered {total_tools} tools across {len(self.toolkits) - len(failed_toolkits)} toolkits")
        else:
            self.logger.warning("No tools were registered!")
        
        if failed_toolkits:
            self.logger.warning(f"Failed to load toolkits: {', '.join(failed_toolkits)}")

