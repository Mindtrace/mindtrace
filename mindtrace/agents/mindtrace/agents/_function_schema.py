"""Function schema builder following Pydantic AI's pattern.

Key responsibilities:
- Detect if a function takes RunContext as first argument
- Generate JSON schema from type annotations for all non-context parameters
- Validate and coerce incoming args_dict with Pydantic before calling
- Create a `call()` method that handles RunContext injection automatically
- Handle both sync and async functions
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Union, cast, get_args, get_origin

from ._run_context import RunContext


# ---------------------------------------------------------------------------
# JSON schema helpers
# ---------------------------------------------------------------------------

def _type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON schema dict.

    Handles: primitives, Optional[X], Union[X, Y], List[X], Dict[K, V],
    Tuple[X, ...], bytes, and Pydantic BaseModel subclasses.
    Unknown annotations return an empty dict (no constraint).
    """
    if annotation is inspect.Parameter.empty:
        return {}
    if annotation is type(None):
        return {"type": "null"}

    # Python 3.10+ union syntax: X | Y (types.UnionType)
    if sys.version_info >= (3, 10):
        import types as _types
        if isinstance(annotation, _types.UnionType):
            args = get_args(annotation)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _type_to_json_schema(non_none[0])
            return {"anyOf": [_type_to_json_schema(a) for a in non_none]}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # typing.Union / Optional[X]
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_json_schema(non_none[0])
        return {"anyOf": [_type_to_json_schema(a) for a in non_none]}

    # Primitives
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is bytes:
        return {"type": "string", "format": "byte"}

    # list / List[X]
    if annotation is list or origin is list:
        if args:
            return {"type": "array", "items": _type_to_json_schema(args[0])}
        return {"type": "array"}

    # dict / Dict[K, V]
    if annotation is dict or origin is dict:
        if args and len(args) >= 2:
            return {"type": "object", "additionalProperties": _type_to_json_schema(args[1])}
        return {"type": "object"}

    # tuple / Tuple[X, Y, ...]
    if annotation is tuple or origin is tuple:
        if args:
            return {"type": "array", "prefixItems": [_type_to_json_schema(a) for a in args]}
        return {"type": "array"}

    # Pydantic BaseModel subclass → use its own schema
    try:
        from pydantic import BaseModel
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            return annotation.model_json_schema()
    except ImportError:
        pass

    # typing.Any → no constraint
    try:
        from typing import Any as _Any
        if annotation is _Any:
            return {}
    except ImportError:
        pass

    # Unknown — emit no constraint so the model can pass anything
    return {}


# ---------------------------------------------------------------------------
# FunctionSchema
# ---------------------------------------------------------------------------

@dataclass(kw_only=True)
class FunctionSchema:
    """Schema information about a function and how to call it.

    Holds whether the function takes a RunContext, whether it is async,
    its docstring description, and a lazily-built Pydantic validator model
    used to validate and coerce tool arguments before execution.
    """

    function: Callable[..., Any]
    """The function to call."""

    takes_ctx: bool
    """Whether the function takes a RunContext as its first argument."""

    is_async: bool
    """Whether the function is async."""

    description: str | None = None
    """Description extracted from the function's docstring."""

    # Cached Pydantic model; built once in __post_init__
    _validator: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._validator = self._build_validator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parameters_json_schema(self) -> dict[str, Any]:
        """Return a JSON Schema object for the function's non-context parameters.

        Skips the RunContext argument (if present) and *args/**kwargs parameters.
        Parameters without type annotations receive no type constraint ({}).
        """
        try:
            sig = inspect.signature(self.function)
        except ValueError:
            return {"type": "object", "properties": {}, "required": []}

        params = list(sig.parameters.values())
        if self.takes_ctx and params:
            params = params[1:]  # drop RunContext

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in params:
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            properties[param.name] = _type_to_json_schema(param.annotation)
            if param.default is inspect.Parameter.empty:
                required.append(param.name)

        return {"type": "object", "properties": properties, "required": required}

    async def call(self, args_dict: dict[str, Any], ctx: RunContext[Any]) -> Any:
        """Validate *args_dict*, inject RunContext if needed, then call the function.

        Args:
            args_dict: Raw argument dict from the model's tool call (JSON-decoded).
            ctx: The current RunContext, injected as first arg when takes_ctx is True.

        Returns:
            The return value of the wrapped function.

        Raises:
            ValueError: If Pydantic validation of args_dict fails.
        """
        validated = self._validate_args(args_dict)
        args, kwargs = self._call_args(validated, ctx)

        if self.is_async:
            function = cast(Callable[[Any], Awaitable[Any]], self.function)
            return await function(*args, **kwargs)
        else:
            function = cast(Callable[[Any], Any], self.function)
            return function(*args, **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_validator(self) -> Any:
        """Build a Pydantic model that mirrors the non-context parameters.

        Returns None when Pydantic is not installed or the function has no
        inspectable parameters (e.g. built-ins).
        """
        try:
            from pydantic import create_model
        except ImportError:
            return None

        try:
            sig = inspect.signature(self.function)
        except ValueError:
            return None

        params = list(sig.parameters.values())
        if self.takes_ctx and params:
            params = params[1:]

        fields: dict[str, Any] = {}
        for param in params:
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            annotation = (
                param.annotation
                if param.annotation is not inspect.Parameter.empty
                else Any
            )
            if param.default is inspect.Parameter.empty:
                fields[param.name] = (annotation, ...)
            else:
                fields[param.name] = (annotation, param.default)

        if not fields:
            return None

        return create_model("_ToolArgs", **fields)

    def _validate_args(self, args_dict: dict[str, Any]) -> dict[str, Any]:
        """Validate and coerce *args_dict* against the Pydantic validator model.

        Returns the validated (and potentially coerced) dict.
        Raises ValueError with a descriptive message on validation failure.
        Passes *args_dict* through unchanged when no validator is available.
        """
        if self._validator is None:
            return args_dict
        try:
            instance = self._validator(**args_dict)
            return instance.model_dump()
        except Exception as exc:
            raise ValueError(f"Tool argument validation failed: {exc}") from exc

    def _call_args(
        self,
        args_dict: dict[str, Any],
        ctx: RunContext[Any],
    ) -> tuple[list[Any], dict[str, Any]]:
        """Build (positional_args, keyword_args) for the function call.

        Prepends *ctx* to positional args when takes_ctx is True.
        """
        args = [ctx] if self.takes_ctx else []
        return args, args_dict


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def function_schema(
    function: Callable[..., Any],
    takes_ctx: bool | None = None,
) -> FunctionSchema:
    """Build a FunctionSchema from a callable.

    Auto-detects whether the function's first parameter is a RunContext
    by checking its type annotation.

    Args:
        function: The callable to wrap.
        takes_ctx: Override auto-detection. Pass True/False to force.

    Returns:
        A FunctionSchema instance ready to call and introspect.
    """
    try:
        sig = inspect.signature(function)
    except ValueError:
        sig = inspect.signature(lambda: None)

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

    is_async = inspect.iscoroutinefunction(function)
    description = function.__doc__

    return FunctionSchema(
        function=function,
        takes_ctx=takes_ctx,
        is_async=is_async,
        description=description,
    )


def _is_call_ctx(annotation: Any) -> bool:
    """Return True if *annotation* is RunContext or RunContext[...]."""
    return annotation is RunContext or get_origin(annotation) is RunContext


__all__ = [
    'FunctionSchema',
    'function_schema',
]
