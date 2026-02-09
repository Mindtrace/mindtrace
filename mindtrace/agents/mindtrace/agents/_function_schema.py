"""Function schema builder following Pydantic AI's pattern.

This module follows the pattern from `pydantic_ai_slim/pydantic_ai/_function_schema.py`.

Key responsibilities:
- Detect if a function takes RunContext as first argument
- Create a `call()` method that handles RunContext injection automatically
- Handle both sync and async functions

Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py`
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast, get_origin

from ._run_context import RunContext


@dataclass(kw_only=True)
class FunctionSchema:
    """Schema information about a function and how to call it.
    
    This follows the pattern from Pydantic AI's FunctionSchema.
    Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py:34-72`
    """
    
    function: Callable[..., Any]
    """The function to call."""
    
    takes_ctx: bool
    """Whether the function takes a RunContext as first argument."""
    
    is_async: bool
    """Whether the function is async."""
    
    description: str | None = None
    """Description extracted from docstring."""
    
    async def call(self, args_dict: dict[str, Any], ctx: RunContext[Any]) -> Any:
        """Call the function with proper RunContext injection.
        
        This follows the pattern from FunctionSchema.call() in Pydantic AI:
        1. Prepare args via _call_args() - inject ctx if needed
        2. Call function (await if async)
        
        Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py:49-56`
        
        Args:
            args_dict: Validated arguments for the function
            ctx: RunContext to inject if function takes it
        
        Returns:
            The result of the function call
        """
        args, kwargs = self._call_args(args_dict, ctx)
        
        if self.is_async:
            function = cast(Callable[[Any], Awaitable[Any]], self.function)
            return await function(*args, **kwargs)
        else:
            function = cast(Callable[[Any], Any], self.function)
            # For sync functions, call directly (could use run_in_executor like Pydantic AI)
            return function(*args, **kwargs)
    
    def _call_args(
        self,
        args_dict: dict[str, Any],
        ctx: RunContext[Any],
    ) -> tuple[list[Any], dict[str, Any]]:
        """Prepare args for function call, injecting RunContext if needed.
        
        This follows the pattern from FunctionSchema._call_args():
        - If function takes context, prepend ctx to args
        - Otherwise, just use kwargs
        
        Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py:58-72`
        
        Args:
            args_dict: The validated arguments
            ctx: The RunContext
        
        Returns:
            Tuple of (positional_args, keyword_args)
        """
        # Inject RunContext as first arg if function takes it
        args = [ctx] if self.takes_ctx else []
        kwargs = args_dict
        
        return args, kwargs


def function_schema(
    function: Callable[..., Any],
    takes_ctx: bool | None = None,
) -> FunctionSchema:
    """Build a FunctionSchema from a function.
    
    This follows the pattern from Pydantic AI's function_schema():
    - Inspect function signature
    - Detect if first parameter is RunContext
    - Determine if function is async
    
    Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py:75-224`
    
    Args:
        function: The function to analyze
        takes_ctx: Whether function takes RunContext. If None, auto-detect.
    
    Returns:
        A FunctionSchema instance
    """
    try:
        sig = inspect.signature(function)
    except ValueError:
        # Can't inspect signature (e.g., built-in function)
        sig = inspect.signature(lambda: None)
    
    # Auto-detect if function takes RunContext
    # Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py:118-120`
    if takes_ctx is None:
        params = list(sig.parameters.values())
        if params:
            first_param = params[0]
            if first_param.annotation != inspect.Parameter.empty:
                takes_ctx = _is_call_ctx(first_param.annotation)
            else:
                takes_ctx = False
        else:
            takes_ctx = False
    
    # Determine if function is async
    is_async = inspect.iscoroutinefunction(function)
    
    # Extract description from docstring
    description = function.__doc__
    
    return FunctionSchema(
        function=function,
        takes_ctx=takes_ctx,
        is_async=is_async,
        description=description,
    )


def _is_call_ctx(annotation: Any) -> bool:
    """Check if annotation is RunContext.
    
    Reference: `pydantic_ai_slim/pydantic_ai/_function_schema.py:300-302`
    
    Args:
        annotation: The type annotation to check
    
    Returns:
        True if annotation is RunContext or RunContext[...]
    """
    return annotation is RunContext or get_origin(annotation) is RunContext


__all__ = [
    'FunctionSchema',
    'function_schema',
]
