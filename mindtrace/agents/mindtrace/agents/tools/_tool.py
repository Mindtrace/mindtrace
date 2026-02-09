"""Tools core API for mindtrace agents.

This module provides the public API for tools, re-exporting core types
and defining tool-related type aliases.

MINIMAL STARTER VERSION - This is the bare minimum to get started.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Concatenate, Generic, TypeAlias
from typing_extensions import ParamSpec, TypeVar

# Import from parent internal modules (tools package is under mindtrace.agents)
from .._run_context import AgentDepsT, RunContext
from .._function_schema import FunctionSchema, function_schema

# Type variable for tool function parameters
ToolParams = ParamSpec('ToolParams')
"""Type variable for tool function parameters."""

# Type aliases for different tool function signatures
ToolFuncContext: TypeAlias = Callable[Concatenate[RunContext[Any], ToolParams], Any]
"""A tool function that takes `RunContext` as the first argument.

Example:
    ```python
    def my_tool(ctx: RunContext[str], x: int, y: str) -> str:
        return f"{ctx.deps}: {x} {y}"
    ```
"""

ToolFuncPlain: TypeAlias = Callable[ToolParams, Any]
"""A tool function that does NOT take `RunContext` as the first argument.

Example:
    ```python
    def my_tool(x: int, y: str) -> str:
        return f"{x} {y}"
    ```
"""

ToolFuncEither: TypeAlias = ToolFuncContext[ToolParams] | ToolFuncPlain[ToolParams]
"""Either kind of tool function - with or without RunContext.

This accepts both:
- Functions that take `RunContext` as first argument
- Functions that don't take `RunContext`
"""

# Type variable for Tool class
ToolAgentDepsT = TypeVar('ToolAgentDepsT')
"""Type variable for agent dependencies in a Tool."""


@dataclass(init=False)
class Tool(Generic[ToolAgentDepsT]):
    """A tool function wrapper for mindtrace agents.
    
    This follows the pattern from Pydantic AI's Tool class:
    - Wraps a function with FunctionSchema
    - FunctionSchema handles RunContext injection
    - Provides tool_def() for model API
    
    Reference: `pydantic_ai_slim/pydantic_ai/tools.py:266-461`
    
    Example:
        ```python
        from mindtrace_starter import Tool, RunContext
        
        def my_tool(ctx: RunContext[str], x: int) -> str:
            return f"{ctx.deps}: {x}"
        
        tool = Tool(my_tool)
        ```
    """
    
    function: Callable[..., Any]
    """The function that implements the tool."""
    
    function_schema: FunctionSchema
    """Schema information about the function, including how to call it with RunContext injection."""
    
    name: str
    """Name of the tool."""
    
    description: str | None
    """Description of what the tool does."""
    
    max_retries: int | None = None
    """Maximum number of retries for this tool."""
    
    def __init__(
        self,
        function: Callable[..., Any],
        *,
        takes_ctx: bool | None = None,
        name: str | None = None,
        description: str | None = None,
        max_retries: int | None = None,
        function_schema_obj: FunctionSchema | None = None,
    ):
        """Create a new tool.
        
        This follows the pattern from Pydantic AI's Tool.__init__:
        - Creates FunctionSchema to handle RunContext injection
        - Extracts name and description
        
        Reference: `pydantic_ai_slim/pydantic_ai/tools.py:290-386`
        
        Args:
            function: The function to wrap
            takes_ctx: Whether function takes RunContext. If None, auto-detect.
            name: Optional name for the tool. Defaults to function.__name__
            description: Optional description of the tool
            max_retries: Maximum number of retries for this tool
            function_schema_obj: Pre-built FunctionSchema (for advanced use)
        """
        self.function = function
        
        # Build FunctionSchema (handles RunContext injection)
        # Reference: `pydantic_ai_slim/pydantic_ai/tools.py:368-374`
        self.function_schema = function_schema_obj or function_schema(
            function,
            takes_ctx=takes_ctx,
        )
        
        self.name = name or function.__name__
        self.description = description or self.function_schema.description
        self.max_retries = max_retries
    
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the wrapped function."""
        return self.function(*args, **kwargs)

    def tool_def(self) -> 'ToolDefinition':
        """Convert this Tool to a ToolDefinition for sending to models.
        
        Reference: `pydantic_ai_slim/pydantic_ai/tools.py:433-444`
        
        Returns:
            A ToolDefinition with basic information.
        """
        # In full implementation, function_schema would have json_schema
        # For minimal version, use placeholder
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters_json_schema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        )


@dataclass
class ToolDefinition:
    """Definition of a tool passed to a model.
    
    This represents a tool in a format that can be sent to LLM APIs.
    It includes the JSON schema for the tool's parameters.
    
    Example:
        ```python
        tool_def = ToolDefinition(
            name='get_weather',
            description='Get weather for a city',
            parameters_json_schema={
                'type': 'object',
                'properties': {
                    'city': {'type': 'string', 'description': 'City name'}
                },
                'required': ['city']
            }
        )
        ```
    """
    
    name: str
    """The name of the tool."""
    
    parameters_json_schema: dict[str, Any] = field(
        default_factory=lambda: {'type': 'object', 'properties': {}, 'required': []}
    )
    """The JSON schema for the tool's parameters.
    
    This follows the JSON Schema specification and describes what
    arguments the tool accepts.
    """
    
    description: str | None = None
    """The description of the tool.
    
    This tells the model when and how to use the tool.
    """
    
    strict: bool | None = None
    """Whether to enforce strict JSON schema validation for tool calls.
    
    When True, the model must strictly match the schema.
    When False or None, the model has more flexibility.
    """
    
    kind: str = 'function'
    """The kind of tool.
    
    Options:
    - 'function': A tool that will be executed and its result returned to the model
    - 'output': A tool that passes through an output value that ends the run
    """
