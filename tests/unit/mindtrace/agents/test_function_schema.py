"""Unit tests for mindtrace.agents._function_schema."""

import pytest

from mindtrace.agents._function_schema import function_schema
from mindtrace.agents._run_context import RunContext


class TestTypeToJsonSchema:
    """Tests for _type_to_json_schema via FunctionSchema.parameters_json_schema."""

    def test_str_param(self):
        """String parameter maps to JSON string type."""

        def fn(name: str) -> str: ...

        schema = function_schema(fn)
        props = schema.parameters_json_schema()["properties"]
        assert props["name"] == {"type": "string"}

    def test_int_param(self):
        """Integer parameter maps to JSON integer type."""

        def fn(count: int) -> int: ...

        schema = function_schema(fn)
        props = schema.parameters_json_schema()["properties"]
        assert props["count"] == {"type": "integer"}

    def test_float_param(self):
        """Float parameter maps to JSON number type."""

        def fn(value: float) -> float: ...

        schema = function_schema(fn)
        props = schema.parameters_json_schema()["properties"]
        assert props["value"] == {"type": "number"}

    def test_bool_param(self):
        """Bool parameter maps to JSON boolean type."""

        def fn(flag: bool) -> bool: ...

        schema = function_schema(fn)
        props = schema.parameters_json_schema()["properties"]
        assert props["flag"] == {"type": "boolean"}

    def test_list_param(self):
        """List[str] parameter maps to JSON array type with string items."""

        def fn(items: list[str]) -> list: ...

        schema = function_schema(fn)
        props = schema.parameters_json_schema()["properties"]
        assert props["items"] == {"type": "array", "items": {"type": "string"}}

    def test_dict_param(self):
        """Dict[str, int] parameter maps to JSON object type."""

        def fn(mapping: dict[str, int]) -> dict: ...

        schema = function_schema(fn)
        props = schema.parameters_json_schema()["properties"]
        assert props["mapping"]["type"] == "object"

    def test_required_vs_optional(self):
        """Parameters without defaults are listed as required."""

        def fn(required_param: str, optional_param: int = 0) -> str: ...

        schema = function_schema(fn)
        result = schema.parameters_json_schema()
        assert "required_param" in result["required"]
        assert "optional_param" not in result["required"]


class TestFunctionSchemaFactory:
    """Tests for the function_schema() factory function."""

    def test_plain_function_takes_ctx_false(self):
        """Plain function (no RunContext) sets takes_ctx=False."""

        def plain(x: int) -> int:
            return x

        schema = function_schema(plain)
        assert schema.takes_ctx is False
        assert schema.is_async is False

    def test_context_function_takes_ctx_true(self):
        """Function whose first param is RunContext sets takes_ctx=True."""

        def with_ctx(ctx: RunContext, x: int) -> int:
            return x

        schema = function_schema(with_ctx)
        assert schema.takes_ctx is True

    def test_async_function_detected(self):
        """Async function sets is_async=True."""

        async def async_fn(x: int) -> int:
            return x

        schema = function_schema(async_fn)
        assert schema.is_async is True

    def test_docstring_as_description(self):
        """Function docstring is captured as description."""

        def documented(x: int) -> int:
            """A helpful description."""
            return x

        schema = function_schema(documented)
        assert schema.description == "A helpful description."

    def test_no_params_function(self):
        """Zero-param function produces empty schema."""

        def no_params() -> str:
            return "hello"

        schema = function_schema(no_params)
        result = schema.parameters_json_schema()
        assert result["properties"] == {}
        assert result["required"] == []

    def test_explicit_takes_ctx_override(self):
        """takes_ctx can be overridden explicitly."""

        def fn(ctx, x: int) -> int:
            return x

        schema = function_schema(fn, takes_ctx=False)
        assert schema.takes_ctx is False


class TestFunctionSchemaCall:
    """Tests for FunctionSchema.call() argument validation and invocation."""

    async def test_sync_call(self):
        """Sync function is called correctly with validated args."""

        def add(a: int, b: int) -> int:
            return a + b

        schema = function_schema(add)
        ctx = RunContext(deps=None)
        result = await schema.call({"a": 3, "b": 4}, ctx)
        assert result == 7

    async def test_async_call(self):
        """Async function is awaited and returns correctly."""

        async def multiply(a: int, b: int) -> int:
            return a * b

        schema = function_schema(multiply)
        ctx = RunContext(deps=None)
        result = await schema.call({"a": 3, "b": 5}, ctx)
        assert result == 15

    async def test_context_injected(self):
        """RunContext is injected as first argument for ctx-taking functions."""

        def get_step(ctx: RunContext, x: int) -> int:
            return ctx.step + x

        schema = function_schema(get_step)
        ctx = RunContext(deps=None, step=10)
        result = await schema.call({"x": 5}, ctx)
        assert result == 15

    async def test_validation_error_on_bad_args(self):
        """Invalid argument types raise ValueError."""

        def fn(x: int) -> int:
            return x

        schema = function_schema(fn)
        ctx = RunContext(deps=None)
        with pytest.raises(ValueError, match="Tool argument validation failed"):
            await schema.call({"x": "not_an_int_and_not_coercible"}, ctx)

    async def test_optional_param_uses_default(self):
        """Optional parameters fall back to defaults when omitted."""

        def fn(x: int, y: int = 100) -> int:
            return x + y

        schema = function_schema(fn)
        ctx = RunContext(deps=None)
        result = await schema.call({"x": 5}, ctx)
        assert result == 105
