"""Tests for the @endpoint decorator and endpoint collection logic."""

from mindtrace.core import TaskSchema
from mindtrace.services import Service, endpoint
from mindtrace.services.core.endpoint_spec import EndpointSpec

# ---------------------------------------------------------------------------
# Minimal schemas for testing
# ---------------------------------------------------------------------------
_test_schema = TaskSchema(name="test")
_other_schema = TaskSchema(name="other")


# ---------------------------------------------------------------------------
# Test: decorator stamps _endpoint_spec on the function
# ---------------------------------------------------------------------------


class TestEndpointDecorator:
    def test_stamps_endpoint_spec(self):
        @endpoint("my_path", schema=_test_schema)
        def handler(self):
            pass

        assert hasattr(handler, "_endpoint_spec")
        spec = handler._endpoint_spec
        assert isinstance(spec, EndpointSpec)
        assert spec.path == "my_path"
        assert spec.method_name == "handler"
        assert spec.schema is _test_schema
        assert spec.methods == ("POST",)
        assert spec.as_tool is False

    def test_all_kwargs_forwarded(self):
        custom_autolog = {"log_level": 10}
        custom_route = {"tags": ["test"]}

        @endpoint(
            "p",
            schema=_test_schema,
            methods=("GET",),
            scope="private",
            as_tool=True,
            autolog_kwargs=custom_autolog,
            api_route_kwargs=custom_route,
        )
        def handler(self):
            pass

        spec = handler._endpoint_spec
        assert spec.methods == ("GET",)
        assert spec.scope == "private"
        assert spec.as_tool is True
        assert spec.autolog_kwargs == custom_autolog
        assert spec.api_route_kwargs == custom_route

    def test_schema_none_supported(self):
        @endpoint("stream/start", methods=("GET",))
        def start_stream(self):
            pass

        assert start_stream._endpoint_spec.schema is None

    def test_preserves_original_function(self):
        @endpoint("echo", schema=_test_schema)
        def echo(self, payload):
            """My docstring."""
            return payload

        assert echo.__name__ == "echo"
        assert echo.__doc__ == "My docstring."
        assert echo(None, "hello") == "hello"


# ---------------------------------------------------------------------------
# Test: __init_subclass__ collects decorated methods
# ---------------------------------------------------------------------------


class TestEndpointCollection:
    def test_collects_decorated_methods(self):
        class MyService(Service):
            @endpoint("foo", schema=_test_schema)
            def foo(self):
                pass

        assert "foo" in MyService.__endpoints__
        assert MyService.__endpoints__["foo"].method_name == "foo"

    def test_inherits_base_service_endpoints(self):
        class MyService(Service):
            @endpoint("custom", schema=_test_schema)
            def custom(self):
                pass

        # Should have the 7 base Service endpoints + custom
        assert "endpoints" in MyService.__endpoints__
        assert "status" in MyService.__endpoints__
        assert "heartbeat" in MyService.__endpoints__
        assert "shutdown" in MyService.__endpoints__
        assert "custom" in MyService.__endpoints__

    def test_subclass_overrides_base_endpoint(self):
        class MyService(Service):
            @endpoint("status", schema=_other_schema)
            def status_func(self):
                return {"status": "custom"}

        spec = MyService.__endpoints__["status"]
        assert spec.schema is _other_schema

    def test_multi_level_inheritance(self):
        class Base(Service):
            @endpoint("base_only", schema=_test_schema)
            def base_handler(self):
                pass

        class Child(Base):
            @endpoint("child_only", schema=_other_schema)
            def child_handler(self):
                pass

        assert "base_only" in Child.__endpoints__
        assert "child_only" in Child.__endpoints__
        # Also inherits Service base endpoints
        assert "endpoints" in Child.__endpoints__


# ---------------------------------------------------------------------------
# Test: Service base class bootstrap
# ---------------------------------------------------------------------------


class TestServiceBaseEndpoints:
    def test_service_has_all_base_endpoints(self):
        expected = {"endpoints", "status", "heartbeat", "server_id", "class_name", "pid_file", "shutdown"}
        assert expected.issubset(Service.__endpoints__.keys())

    def test_base_endpoint_specs_correct(self):
        assert Service.__endpoints__["endpoints"].as_tool is True
        assert Service.__endpoints__["status"].as_tool is True
        assert Service.__endpoints__["heartbeat"].as_tool is True
        assert Service.__endpoints__["server_id"].as_tool is False
        assert Service.__endpoints__["shutdown"].autolog_kwargs == {"log_level": 10}
