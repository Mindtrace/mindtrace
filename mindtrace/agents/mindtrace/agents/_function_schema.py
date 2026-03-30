from __future__ import annotations

import inspect
import sys
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Union, cast, get_args, get_origin

from ._run_context import RunContext


def _type_to_json_schema(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty:
        return {}
    if annotation is type(None):
        return {"type": "null"}

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

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_json_schema(non_none[0])
        return {"anyOf": [_type_to_json_schema(a) for a in non_none]}

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

    if annotation is list or origin is list:
        if args:
            return {"type": "array", "items": _type_to_json_schema(args[0])}
        return {"type": "array"}

    if annotation is dict or origin is dict:
        if args and len(args) >= 2:
            return {"type": "object", "additionalProperties": _type_to_json_schema(args[1])}
        return {"type": "object"}

    if annotation is tuple or origin is tuple:
        if args:
            return {"type": "array", "prefixItems": [_type_to_json_schema(a) for a in args]}
        return {"type": "array"}

    try:
        from pydantic import BaseModel

        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            return annotation.model_json_schema()
    except ImportError:
        pass

    try:
        from typing import Any as _Any

        if annotation is _Any:
            return {}
    except ImportError:
        pass

    return {}


@dataclass(kw_only=True)
class FunctionSchema:
    function: Callable[..., Any]
    takes_ctx: bool
    is_async: bool
    description: str | None = None
    _hints: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _validator: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self._hints = typing.get_type_hints(self.function)
        except Exception:
            self._hints = {}
        self._validator = self._build_validator()

    def parameters_json_schema(self) -> dict[str, Any]:
        try:
            sig = inspect.signature(self.function)
        except ValueError:
            return {"type": "object", "properties": {}, "required": []}

        params = list(sig.parameters.values())
        if self.takes_ctx and params:
            params = params[1:]

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in params:
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            annotation = self._hints.get(param.name, param.annotation)
            properties[param.name] = _type_to_json_schema(annotation)
            if param.default is inspect.Parameter.empty:
                required.append(param.name)

        return {"type": "object", "properties": properties, "required": required}

    async def call(self, args_dict: dict[str, Any], ctx: RunContext[Any]) -> Any:
        validated = self._validate_args(args_dict)
        args, kwargs = self._call_args(validated, ctx)
        if self.is_async:
            function = cast(Callable[[Any], Awaitable[Any]], self.function)
            return await function(*args, **kwargs)
        else:
            function = cast(Callable[[Any], Any], self.function)
            return function(*args, **kwargs)

    def _build_validator(self) -> Any:
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
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            annotation = self._hints.get(
                param.name,
                param.annotation if param.annotation is not inspect.Parameter.empty else Any,
            )
            if param.default is inspect.Parameter.empty:
                fields[param.name] = (annotation, ...)
            else:
                fields[param.name] = (annotation, param.default)

        if not fields:
            return None

        return create_model("_ToolArgs", **fields)

    def _validate_args(self, args_dict: dict[str, Any]) -> dict[str, Any]:
        if self._validator is None:
            return args_dict
        try:
            instance = self._validator(**args_dict)
            return instance.model_dump()
        except Exception as exc:
            raise ValueError(f"Tool argument validation failed: {exc}") from exc

    def _call_args(self, args_dict: dict[str, Any], ctx: RunContext[Any]) -> tuple[list[Any], dict[str, Any]]:
        args = [ctx] if self.takes_ctx else []
        return args, args_dict


def function_schema(function: Callable[..., Any], takes_ctx: bool | None = None) -> FunctionSchema:
    try:
        sig = inspect.signature(function)
    except ValueError:
        sig = inspect.signature(lambda: None)

    if takes_ctx is None:
        params = list(sig.parameters.values())
        if params:
            first_param = params[0]
            try:
                hints = typing.get_type_hints(function)
                annotation = hints.get(first_param.name, first_param.annotation)
            except Exception:
                annotation = first_param.annotation
            if annotation != inspect.Parameter.empty:
                takes_ctx = _is_call_ctx(annotation)
            else:
                takes_ctx = False
        else:
            takes_ctx = False

    is_async = inspect.iscoroutinefunction(function)
    description = function.__doc__

    return FunctionSchema(function=function, takes_ctx=takes_ctx, is_async=is_async, description=description)


def _is_call_ctx(annotation: Any) -> bool:
    return annotation is RunContext or get_origin(annotation) is RunContext


__all__ = ["FunctionSchema", "function_schema"]
