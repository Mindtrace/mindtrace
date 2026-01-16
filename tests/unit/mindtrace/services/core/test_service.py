from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import psutil
import pytest
import requests
from fastapi import HTTPException
from pydantic import BaseModel
from urllib3.util.url import parse_url

from mindtrace.core import TaskSchema
from mindtrace.services import ServerStatus, Service


@pytest.fixture(autouse=True)
def _set_minimal_env(monkeypatch):
    """Provide minimal env so tests don't need to patch class config."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")
    # Reload class-level config each test to pick up env
    from mindtrace.core import CoreConfig

    Service.config = CoreConfig()


class SampleInput(BaseModel):
    message: str
    count: int = 1


class SampleOutput(BaseModel):
    result: str
    processed_count: int


class SampleService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add a test task
        test_task = TaskSchema(
            name="test_task",
            input_schema=SampleInput,
            output_schema=SampleOutput,
        )
        self.add_endpoint("test_task", self.test_handler, schema=test_task)

        # Add another task for multiple task testing
        echo_task = TaskSchema(
            name="echo",
            input_schema=SampleInput,
            output_schema=SampleOutput,
        )
        self.add_endpoint("echo", self.echo_handler, schema=echo_task)

    def test_handler(self, payload: SampleInput) -> SampleOutput:
        return SampleOutput(result=f"Processed: {payload.message}", processed_count=payload.count * 2)

    def echo_handler(self, payload: SampleInput) -> SampleOutput:
        return SampleOutput(result=payload.message, processed_count=payload.count)


class TestServiceClass:
    """Test the Service class functionality"""

    def test_service_initialization(self):
        service = SampleService()
        # Check that our custom endpoints are present (plus system endpoints)
        assert "test_task" in service.endpoints
        assert "echo" in service.endpoints
        # Verify system endpoints are also present
        assert "status" in service.endpoints
        assert "heartbeat" in service.endpoints

    def test_task_schema_registration(self):
        service = SampleService()

        # Check test_task
        test_task = service.endpoints["test_task"]
        assert test_task.name == "test_task"
        assert test_task.input_schema == SampleInput
        assert test_task.output_schema == SampleOutput

        # Check echo task
        echo_task = service.endpoints["echo"]
        assert echo_task.name == "echo"
        assert echo_task.input_schema == SampleInput
        assert echo_task.output_schema == SampleOutput

    def test_add_endpoint_without_task(self):
        service = Service()

        def dummy_handler():
            return {"status": "ok"}

        # The schema parameter is now required, so this should raise TypeError
        with pytest.raises(TypeError):
            service.add_endpoint("dummy", dummy_handler)  # type: ignore


class TestServiceInitialization:
    """Test Service initialization and ID generation."""

    @patch("mindtrace.services.core.service.Path")
    def test_generate_id_and_pid_file_default(self, mock_path):
        """Test _generate_id_and_pid_file with default parameters."""
        mock_path.return_value.parent.mkdir = Mock()

        with patch("mindtrace.services.core.service.uuid.uuid1") as mock_uuid:
            test_uuid = UUID("12345678-1234-5678-1234-567812345678")
            mock_uuid.return_value = test_uuid

            unique_id, pid_file = Service._generate_id_and_pid_file()

            assert unique_id == test_uuid
            assert str(test_uuid) in pid_file
            assert "Service" in pid_file
            mock_path.return_value.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("mindtrace.services.core.service.Path")
    def test_generate_id_and_pid_file_with_unique_id(self, mock_path):
        """Test _generate_id_and_pid_file with provided unique_id."""
        mock_path.return_value.parent.mkdir = Mock()

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        unique_id, pid_file = Service._generate_id_and_pid_file(unique_id=test_uuid)

        assert unique_id == test_uuid
        assert str(test_uuid) in pid_file

    @patch("mindtrace.services.core.service.Path")
    def test_generate_id_and_pid_file_with_pid_file(self, mock_path):
        """Test _generate_id_and_pid_file with provided pid_file."""
        mock_path.return_value.parent.mkdir = Mock()

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_pid_file = f"/tmp/Service_{test_uuid}_pid.txt"

        unique_id, pid_file = Service._generate_id_and_pid_file(pid_file=test_pid_file)

        assert unique_id == test_uuid
        assert pid_file == test_pid_file

    @patch("mindtrace.services.core.service.Path")
    def test_generate_id_and_pid_file_mismatch_error(self, mock_path):
        """Test _generate_id_and_pid_file raises error when unique_id not in pid_file."""
        mock_path.return_value.parent.mkdir = Mock()

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        wrong_pid_file = "/tmp/Service_different-uuid_pid.txt"

        with pytest.raises(ValueError, match="unique_id .* not found in pid_file"):
            Service._generate_id_and_pid_file(unique_id=test_uuid, pid_file=wrong_pid_file)

    def test_server_id_to_pid_file(self):
        """Test _server_id_to_pid_file method."""
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")

        pid_file = Service._server_id_to_pid_file(test_uuid)

        expected = f"/tmp/pids/Service_{test_uuid}_pid.txt"
        assert pid_file == expected

    def test_pid_file_to_server_id(self):
        """Test _pid_file_to_server_id method."""
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        pid_file = f"/tmp/pids/Service_{test_uuid}_pid.txt"

        extracted_uuid = Service._pid_file_to_server_id(pid_file)
        assert extracted_uuid == test_uuid


class TestServiceStatusAndConnection:
    """Test Service status checking and connection methods."""

    @patch("mindtrace.services.core.service.requests.request")
    def test_status_at_host_available(self, mock_request):
        """Test status_at_host when service is available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "Available"}
        mock_request.return_value = mock_response

        status = Service.status_at_host("http://localhost:8000")

        assert status == ServerStatus.AVAILABLE
        mock_request.assert_called_once_with("POST", "http://localhost:8000/status", timeout=60)

    @patch("mindtrace.services.core.service.requests.request")
    def test_status_at_host_connection_error(self, mock_request):
        """Test status_at_host when connection fails."""
        mock_request.side_effect = requests.exceptions.ConnectionError()

        status = Service.status_at_host("http://localhost:8000")

        assert status == ServerStatus.DOWN

    @patch("mindtrace.services.core.service.requests.request")
    def test_status_at_host_bad_status_code(self, mock_request):
        """Test status_at_host when response has bad status code."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_request.return_value = mock_response

        status = Service.status_at_host("http://localhost:8000")

        assert status == ServerStatus.DOWN

    @patch.object(Service, "status_at_host")
    @patch.object(Service, "default_url")
    def test_connect_success_with_default_manager(self, mock_default_url, mock_status_at_host):
        """Test connect method success with default connection manager."""
        mock_default_url.return_value = parse_url("http://localhost:8000")
        mock_status_at_host.return_value = ServerStatus.AVAILABLE

        with patch("mindtrace.services.core.service.generate_connection_manager") as mock_generate:
            mock_manager_class = Mock()
            mock_manager_instance = Mock()
            mock_manager_class.return_value = mock_manager_instance
            mock_generate.return_value = mock_manager_class

            result = Service.connect()

            assert result == mock_manager_instance
            mock_generate.assert_called_once_with(Service)
            mock_manager_class.assert_called_once_with(url=mock_default_url.return_value)

    @patch.object(Service, "status_at_host")
    def test_connect_success_with_custom_manager(self, mock_status_at_host):
        """Test connect method success with custom connection manager."""
        mock_status_at_host.return_value = ServerStatus.AVAILABLE

        # Set up custom client interface
        mock_client_interface = Mock()
        mock_manager_instance = Mock()
        mock_client_interface.return_value = mock_manager_instance
        Service._client_interface = mock_client_interface

        try:
            result = Service.connect(url="http://localhost:8000")

            assert result == mock_manager_instance
            mock_client_interface.assert_called_once_with(url=parse_url("http://localhost:8000"))
        finally:
            # Clean up
            Service._client_interface = None

    @patch.object(Service, "status_at_host")
    def test_connect_failure(self, mock_status_at_host):
        """Test connect method when service is not available."""
        mock_status_at_host.return_value = ServerStatus.DOWN

        with pytest.raises(HTTPException) as exc_info:
            Service.connect(url="http://localhost:8000")

        assert exc_info.value.status_code == 503
        assert "Server failed to connect" in str(exc_info.value.detail)


class TestServiceProperties:
    """Test Service properties and methods."""

    def test_endpoints_property(self):
        """Test endpoints property returns correct endpoints."""
        service = SampleService()
        endpoints = service.endpoints

        assert isinstance(endpoints, dict)
        assert "test_task" in endpoints
        assert "echo" in endpoints
        assert "status" in endpoints

    def test_status_property(self):
        """Test status property returns current status."""
        service = SampleService()

        # Default status should be AVAILABLE after initialization
        assert service.status == ServerStatus.AVAILABLE

    def test_heartbeat_method(self):
        """Test heartbeat method returns proper Heartbeat object."""
        service = SampleService()
        heartbeat = service.heartbeat()

        assert heartbeat.status == service.status
        assert heartbeat.server_id == service.id
        assert heartbeat.message is not None and "Heartbeat check successful" in heartbeat.message
        assert heartbeat.details is None

    def test_endpoints_func(self):
        """Test endpoints_func method."""
        service = SampleService()
        result = service.endpoints_func()

        assert isinstance(result, dict)
        assert "endpoints" in result
        assert isinstance(result["endpoints"], list)
        assert "test_task" in result["endpoints"]
        assert "echo" in result["endpoints"]

    def test_status_func(self):
        """Test status_func method."""
        service = SampleService()
        result = service.status_func()

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == service.status.value

    def test_heartbeat_func(self):
        """Test heartbeat_func method."""
        service = SampleService()
        result = service.heartbeat_func()

        assert isinstance(result, dict)
        assert "heartbeat" in result
        assert isinstance(result["heartbeat"], type(service.heartbeat()))
        assert result["heartbeat"].status == service.status


class TestServiceMCP:
    """Test Service MCP app integration and mounting."""

    def test_service_creates_mcp_and_mcp_app(self):
        service = Service()
        # FastMCP instance should be created
        assert hasattr(service, "mcp"), "Service should have an 'mcp' attribute."
        # mcp_app should be created
        assert hasattr(service, "mcp_app"), "Service should have an 'mcp_app' attribute."
        # mcp_app should be a FastAPI app (or compatible)
        from fastapi import FastAPI
        from starlette.applications import Starlette

        assert isinstance(service.mcp_app, (FastAPI, Starlette)), "mcp_app should be a FastAPI or Starlette app."

    def test_service_mounts_mcp_app(self):
        service = Service()
        # The /mcp-server route should be mounted
        routes = [route for route in service.app.routes if hasattr(route, "path")]
        mcp_mounts = [route for route in routes if getattr(route, "path", None) == "/mcp-server"]
        assert mcp_mounts, "Service.app should have /mcp-server mounted."
        # The mounted app should be the mcp_app
        # In FastAPI, mounts are in app.routes as Mount objects
        from fastapi.routing import Mount

        found = False
        for route in service.app.routes:
            if isinstance(route, Mount) and route.path == "/mcp-server":
                assert route.app is service.mcp_app, "Mounted /mcp-server should be service.mcp_app."
                found = True
        assert found, "/mcp-server mount not found as a Mount route."

    def test_add_tool_registers_with_mcp(self):
        service = Service()
        # Patch the mcp.tool decorator to track registration
        called = {}

        def fake_tool(name, **kwargs):
            def decorator(func):
                called["name"] = name
                called["func"] = func
                called["kwargs"] = kwargs
                return func

            return decorator

        service.mcp.tool = fake_tool

        def dummy_func():
            return "ok"

        service.add_tool("dummy_tool", dummy_func)
        assert called["name"] == "dummy_tool"
        assert called["func"] is dummy_func

    def test_add_endpoint_with_as_tool_calls_add_tool(self):
        service = Service()
        # Patch add_tool to track calls
        called = {}

        def fake_add_tool(tool_name, func):
            called["tool_name"] = tool_name
            called["func"] = func

        service.add_tool = fake_add_tool

        def dummy_func():
            return "ok"

        test_schema = TaskSchema(name="dummy", input_schema=None, output_schema=None)
        service.add_endpoint("dummy", dummy_func, schema=test_schema, as_tool=True)
        assert called["tool_name"] == "dummy"
        assert called["func"] is dummy_func

    def test_get_mcp_paths_normalizes_paths(self, monkeypatch):
        """Test get_mcp_paths normalizes paths that don't start with /."""
        # Set config to paths without leading slashes
        monkeypatch.setenv("MINDTRACE_MCP__HTTP_APP_PATH", "mcp")
        monkeypatch.setenv("MINDTRACE_MCP__MOUNT_PATH", "mcp-server")
        from mindtrace.core import CoreConfig

        Service.config = CoreConfig()

        mount_path, http_app_path = Service.get_mcp_paths()

        # Should add leading slashes
        assert mount_path == "/mcp-server"
        assert http_app_path == "/mcp"

    def test_get_mcp_paths_preserves_existing_slashes(self, monkeypatch):
        """Test get_mcp_paths preserves paths that already start with /."""
        # Set config to paths with leading slashes
        monkeypatch.setenv("MINDTRACE_MCP__HTTP_APP_PATH", "/mcp")
        monkeypatch.setenv("MINDTRACE_MCP__MOUNT_PATH", "/mcp-server")
        from mindtrace.core import CoreConfig

        Service.config = CoreConfig()

        mount_path, http_app_path = Service.get_mcp_paths()

        # Should keep leading slashes
        assert mount_path == "/mcp-server"
        assert http_app_path == "/mcp"


class TestServiceUrlBuilding:
    """Test Service URL building functionality."""

    @patch.object(Service, "default_url")
    def test_build_url_with_explicit_url_string(self, mock_default_url):
        """Test build_url with explicit URL string."""
        result = Service.build_url(url="http://example.com:9000")

        assert str(result) == "http://example.com:9000/"
        mock_default_url.assert_not_called()

    @patch.object(Service, "default_url")
    def test_build_url_with_explicit_url_object(self, mock_default_url):
        """Test build_url with explicit URL object."""
        url_obj = parse_url("http://example.com:9000")
        result = Service.build_url(url=url_obj)

        assert result == url_obj
        mock_default_url.assert_not_called()

    @patch.object(Service, "default_url")
    def test_build_url_with_host_port(self, mock_default_url):
        """Test build_url with host and port parameters."""
        mock_default_url.return_value = parse_url("http://localhost:8000")

        result = Service.build_url(host="192.168.1.1", port=9000)

        assert str(result) == "http://192.168.1.1:9000/"

    @patch.object(Service, "default_url")
    def test_build_url_with_host_only(self, mock_default_url):
        """Test build_url with host only (uses default port)."""
        mock_default_url.return_value = parse_url("http://localhost:8000")

        result = Service.build_url(host="192.168.1.1")

        assert str(result) == "http://192.168.1.1:8000/"

    @patch.object(Service, "default_url")
    def test_build_url_with_port_only(self, mock_default_url):
        """Test build_url with port only (uses default host)."""
        mock_default_url.return_value = parse_url("http://localhost:8000")

        result = Service.build_url(port=9000)

        assert str(result) == "http://localhost:9000/"

    @patch.object(Service, "default_url")
    def test_build_url_defaults(self, mock_default_url):
        """Test build_url with no parameters (uses defaults)."""
        mock_default_url.return_value = parse_url("http://localhost:8000")

        result = Service.build_url()

        assert result == mock_default_url.return_value
        mock_default_url.assert_called_once()

    def test_default_url_service_specific(self, monkeypatch):
        """Test default_url returns URL from SERVICE when set via env (no config patch)."""
        monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://service.example.com:8080")
        # Force reload of class-level config to pick up new env
        from mindtrace.core import CoreConfig

        Service.config = CoreConfig()
        result = Service.default_url()
        assert str(result) == "http://service.example.com:8080"

    @patch.object(Service, "default_url")
    def test_default_url_server_base(self, mock_default_url):
        """Test build_url uses default_url when no url/host/port provided (no config patch)."""
        mock_default_url.return_value = parse_url("http://base.example.com:8080")
        result = Service.build_url()
        assert str(result) == "http://base.example.com:8080"

    def test_default_url_fallback(self, monkeypatch):
        """Test default_url returns fallback URL when no config/env found (no config patch)."""
        # Ensure no env for SERVICE is set; rely on code fallback
        monkeypatch.delenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", raising=False)
        from mindtrace.core import CoreConfig

        Service.config = CoreConfig()
        result = Service.default_url()

        assert str(result) == "http://localhost:8000"


class TestServiceMethods:
    """Test additional Service methods."""

    def test_register_connection_manager(self):
        """Test register_connection_manager method."""
        mock_manager = Mock()

        # Clean up any existing client interface
        original_interface = Service._client_interface

        try:
            Service.register_connection_manager(mock_manager)
            assert Service._client_interface == mock_manager
        finally:
            # Restore original state
            Service._client_interface = original_interface

    def test_default_log_file(self, monkeypatch):
        """Test default_log_file method without patching config by setting env."""
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
        result = Service.default_log_file()

        expected = "/tmp/logs/Service_logs.txt"
        assert result == expected

    def test_add_endpoint_with_custom_methods(self):
        """Test add_endpoint with custom HTTP methods."""
        service = Service()

        def test_handler():
            return {"test": "response"}

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with patch.object(service.app, "add_api_route") as mock_add_route:
            service.add_endpoint("test", test_handler, schema=test_schema, methods=["GET", "POST"])

            # Verify the endpoint was added with custom methods
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            assert call_args[1]["methods"] == ["GET", "POST"]

    def test_add_endpoint_with_api_route_kwargs(self):
        """Test add_endpoint with additional API route kwargs."""
        service = Service()

        def test_handler():
            return {"test": "response"}

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with patch.object(service.app, "add_api_route") as mock_add_route:
            service.add_endpoint(
                "test",
                test_handler,
                schema=test_schema,
                api_route_kwargs={"tags": ["test"], "summary": "Test endpoint"},
            )

            # Verify the kwargs were passed through
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            assert call_args[1]["tags"] == ["test"]
            assert call_args[1]["summary"] == "Test endpoint"

    def test_add_endpoint_with_invalid_scope_string(self):
        """Test add_endpoint with invalid scope string defaults to PUBLIC."""
        service = Service()

        def test_handler():
            return {"test": "response"}

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with patch.object(service.app, "add_api_route") as mock_add_route:
            with patch.object(service.logger, "warning") as mock_warning:
                service.add_endpoint(
                    "test",
                    test_handler,
                    schema=test_schema,
                    scope="invalid_scope",  # Invalid scope string
                )

                # Verify warning was logged
                mock_warning.assert_called_once()
                format_string = mock_warning.call_args[0][0]
                format_args = mock_warning.call_args[0][1:]
                assert "Invalid scope" in format_string
                assert "defaulting to PUBLIC" in format_string
                assert len(format_args) > 0
                assert format_args[0] == "invalid_scope"

                # Verify endpoint was still added (with PUBLIC scope)
                mock_add_route.assert_called_once()

    def test_add_endpoint_with_authenticated_scope_adds_auth_dependency(self):
        """Test add_endpoint with AUTHENTICATED scope adds auth dependency."""
        from mindtrace.services.core.types import Scope

        service = Service()

        def test_handler():
            return {"test": "response"}

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with patch.object(service.app, "add_api_route") as mock_add_route:
            service.add_endpoint(
                "test",
                test_handler,
                schema=test_schema,
                scope=Scope.AUTHENTICATED,
            )

            # Verify the endpoint was added with auth dependency
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            dependencies = call_args[1].get("dependencies", [])

            # Should have at least one dependency (the auth dependency)
            assert len(dependencies) > 0
            # Verify it's a Security dependency (from fastapi)

            # Security returns a Security object, check it has the dependency attribute
            assert any(hasattr(dep, "dependency") for dep in dependencies)

    def test_add_endpoint_with_authenticated_scope_string_adds_auth_dependency(self):
        """Test add_endpoint with 'authenticated' scope string adds auth dependency."""
        service = Service()

        def test_handler():
            return {"test": "response"}

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with patch.object(service.app, "add_api_route") as mock_add_route:
            service.add_endpoint(
                "test",
                test_handler,
                schema=test_schema,
                scope="authenticated",  # String scope
            )

            # Verify the endpoint was added with auth dependency
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            dependencies = call_args[1].get("dependencies", [])

            # Should have at least one dependency (the auth dependency)
            assert len(dependencies) > 0
            # Verify it's a Security dependency

            # Security returns a Security object, check it has the dependency attribute
            assert any(hasattr(dep, "dependency") for dep in dependencies)

    def test_add_endpoint_with_authenticated_scope_and_existing_dependencies(self):
        """Test add_endpoint with AUTHENTICATED scope adds auth to existing dependencies."""
        from fastapi import Depends

        from mindtrace.services.core.types import Scope

        service = Service()

        def test_handler():
            return {"test": "response"}

        def existing_dependency():
            return "existing"

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with patch.object(service.app, "add_api_route") as mock_add_route:
            service.add_endpoint(
                "test",
                test_handler,
                schema=test_schema,
                scope=Scope.AUTHENTICATED,
                api_route_kwargs={"dependencies": [Depends(existing_dependency)]},
            )

            # Verify the endpoint was added with both dependencies
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            dependencies = call_args[1].get("dependencies", [])

            # Should have both the existing dependency and auth dependency
            assert len(dependencies) == 2
            # Verify both types are present

            # Security returns a Security object, check it has the dependency attribute
            assert any(hasattr(dep, "dependency") for dep in dependencies)
            # Depends is also a function, check for it differently
            assert any(hasattr(dep, "dependency") or hasattr(dep, "call") for dep in dependencies)


class TestServiceShutdown:
    """Test Service shutdown functionality."""

    @patch("mindtrace.services.core.service.os.kill")
    def test_shutdown_method(self, mock_kill):
        """Test shutdown static method."""
        with patch("mindtrace.services.core.service.os.getppid", return_value=1234):
            with patch("mindtrace.services.core.service.os.getpid", return_value=5678):
                response = Service.shutdown()

                # Should kill parent process first, then self
                assert mock_kill.call_count == 2
                mock_kill.assert_any_call(1234, 15)  # SIGTERM = 15
                mock_kill.assert_any_call(5678, 15)

                # Should return 200 response
                assert response.status_code == 200
                assert "shutting down" in response.body.decode().lower()

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_success(self):
        """Test shutdown_cleanup method success."""
        service = SampleService()

        # Should not raise any exceptions
        await service.shutdown_cleanup()

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_with_exception(self):
        """Test shutdown_cleanup method handles exceptions."""
        service = SampleService()

        # Mock logger to raise exception
        with patch.object(service, "logger") as mock_logger:
            mock_logger.debug.side_effect = Exception("Logger error")

            # Should not raise the exception, but log a warning
            await service.shutdown_cleanup()

            mock_logger.warning.assert_called_once()


class TestServiceLifespan:
    """Test Service FastAPI lifespan functionality."""

    @pytest.mark.asyncio
    async def test_lifespan_context_manager(self):
        """Test FastAPI lifespan context manager."""
        service = SampleService()

        # Get the lifespan function from the FastAPI app
        lifespan_func = service.app.router.lifespan_context

        # Mock the logger and shutdown_cleanup
        with patch.object(service, "logger") as mock_logger:
            with patch.object(service, "shutdown_cleanup", new_callable=AsyncMock) as mock_cleanup:
                # Test the lifespan context manager
                async with lifespan_func(service.app):
                    # Verify startup logging
                    mock_logger.info.assert_called_with(f"Server {service.id} starting up.")

                # After exiting context, shutdown should be called
                mock_cleanup.assert_called_once()
                # Verify shutdown logging
                assert mock_logger.info.call_count == 2
                shutdown_call = mock_logger.info.call_args_list[1]
                assert f"Server {service.id} shut down." in str(shutdown_call)


class TestServiceLaunchExceptionHandling:
    """Test Service launch method exception handling."""

    @patch.object(Service, "status_at_host")
    @patch.object(Service, "build_url")
    def test_launch_runtime_error_handling(self, mock_build_url, mock_status_at_host):
        """Test launch method RuntimeError handling."""
        mock_build_url.return_value = parse_url("http://localhost:8000")
        # Make status_at_host raise RuntimeError
        mock_status_at_host.side_effect = RuntimeError("Connection failed")

        # Create a mock logger and patch it at the class level
        mock_logger = Mock()
        with patch.object(type(Service), "logger", mock_logger, create=True):
            with pytest.raises(RuntimeError, match="Connection failed"):
                Service.launch()

            # Should log warning about service already running
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Another service is already running" in warning_call
            assert "New service was NOT launched" in warning_call

    @patch.object(Service, "status_at_host")
    @patch.object(Service, "build_url")
    def test_launch_service_already_running_http_exception(self, mock_build_url, mock_status_at_host):
        """Test launch method HTTPException when service already running."""
        mock_build_url.return_value = parse_url("http://localhost:8000")
        # Make status_at_host return AVAILABLE (service already running)
        mock_status_at_host.return_value = ServerStatus.AVAILABLE

        with pytest.raises(HTTPException) as exc_info:
            Service.launch()

        # Should raise HTTPException with status 400
        assert exc_info.value.status_code == 400
        assert "already running" in exc_info.value.detail
        assert "Service" in exc_info.value.detail
        assert "http://localhost:8000" in exc_info.value.detail
        assert "ServerStatus.AVAILABLE" in exc_info.value.detail

    @patch.object(Service, "status_at_host")
    @patch.object(Service, "build_url")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_blocking_keyboard_interrupt(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_build_url, mock_status_at_host
    ):
        """Test launch method blocking with KeyboardInterrupt."""
        # Setup mocks
        mock_build_url.return_value = parse_url("http://localhost:8000")
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process that raises KeyboardInterrupt on wait
        mock_process = Mock()
        mock_process.wait.side_effect = KeyboardInterrupt("User interrupted")
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            with patch.object(Service, "_cleanup_server") as mock_cleanup:
                with pytest.raises(KeyboardInterrupt):
                    Service.launch(block=True, wait_for_launch=False)

                # Should call cleanup on KeyboardInterrupt
                mock_cleanup.assert_called_with(test_uuid)

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    def test_launch_connect_raises(self, mock_status_at_host):
        """Test that Service.launch() times out if it takes too long to launch"""
        mock_status_at_host.return_value = ServerStatus.DOWN
        from time import sleep

        from mindtrace.services.core.launcher import Launcher

        def fake_run(*args, **kwargs):
            sleep(30)
            Launcher.run(*args, *kwargs)

        with patch("mindtrace.services.core.launcher.Launcher.run", side_effect=fake_run):
            # Use shorter timeout (0.01s) to speed up test while still testing timeout behavior
            with pytest.raises(TimeoutError):
                Service.launch(timeout=0.01)

    @patch.object(Service, "status_at_host")
    @patch.object(Service, "build_url")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_blocking_finally_cleanup(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_build_url, mock_status_at_host
    ):
        """Test launch method blocking finally block."""
        # Setup mocks
        mock_build_url.return_value = parse_url("http://localhost:8000")
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process that completes normally
        mock_process = Mock()
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            with patch.object(Service, "_cleanup_server") as mock_cleanup:
                result = Service.launch(block=True, wait_for_launch=False)

                # Should call cleanup in finally block
                mock_cleanup.assert_called_with(test_uuid)
                assert result is None  # No connection manager when wait_for_launch=False

        finally:
            # Restore original state
            Service._active_servers = original_servers


class TestServiceCleanupMethods:
    """Test Service cleanup methods with process handling."""

    @patch("mindtrace.services.core.service.psutil.Process")
    def test_cleanup_server_child_no_such_process(self, mock_psutil_process):
        """Test _cleanup_server with child NoSuchProcess exception."""
        # Setup mock process
        mock_process = Mock()
        mock_process.pid = 1234

        # Setup psutil mock
        mock_parent = Mock()
        mock_child = Mock()
        mock_child.terminate.side_effect = psutil.NoSuchProcess(1235)  # Child process not found
        mock_parent.children.return_value = [mock_child]
        mock_parent.terminate.return_value = None
        mock_parent.wait.return_value = None
        mock_psutil_process.return_value = mock_parent

        # Setup active servers
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        original_servers = Service._active_servers.copy()
        Service._active_servers[test_uuid] = mock_process

        try:
            # Should handle NoSuchProcess exception gracefully
            Service._cleanup_server(test_uuid)

            # Should still clean up the parent and remove from active servers
            mock_parent.terminate.assert_called_once()
            mock_parent.wait.assert_called_once_with(timeout=5)
            assert test_uuid not in Service._active_servers

        finally:
            Service._active_servers = original_servers

    @patch("mindtrace.services.core.service.psutil.Process")
    def test_cleanup_server_parent_no_such_process(self, mock_psutil_process):
        """Test _cleanup_server with parent NoSuchProcess exception."""
        # Setup mock process
        mock_process = Mock()
        mock_process.pid = 1234

        # Setup psutil mock - the Process constructor itself raises NoSuchProcess
        mock_psutil_process.side_effect = psutil.NoSuchProcess(1234)  # Process not found

        # Setup active servers
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        original_servers = Service._active_servers.copy()
        Service._active_servers[test_uuid] = mock_process

        try:
            mock_logger = Mock()
            with patch.object(type(Service), "logger", mock_logger, create=True):
                # Should handle NoSuchProcess exception gracefully
                Service._cleanup_server(test_uuid)

                # Should log debug message about process already terminated
                mock_logger.debug.assert_called_with("Process already terminated.")
                # Should still remove from active servers
                assert test_uuid not in Service._active_servers

        finally:
            Service._active_servers = original_servers

    @patch("mindtrace.services.core.service.psutil.Process")
    def test_cleanup_server_parent_terminate_no_such_process(self, mock_psutil_process):
        """Test _cleanup_server with parent terminate NoSuchProcess exception."""
        # Setup mock process
        mock_process = Mock()
        mock_process.pid = 1234

        # Setup psutil mock
        mock_parent = Mock()
        mock_parent.children.return_value = []  # No children
        # Make parent.terminate() raise NoSuchProcess
        mock_parent.terminate.side_effect = psutil.NoSuchProcess(1234)
        mock_parent.wait.return_value = None  # This won't be called due to exception
        mock_psutil_process.return_value = mock_parent

        # Setup active servers
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        original_servers = Service._active_servers.copy()
        Service._active_servers[test_uuid] = mock_process

        try:
            # Should handle NoSuchProcess exception gracefully
            Service._cleanup_server(test_uuid)

            # Should attempt to terminate parent (which raises NoSuchProcess)
            mock_parent.terminate.assert_called_once()
            # Should not call wait since terminate raised exception
            mock_parent.wait.assert_not_called()
            # Should still remove from active servers
            assert test_uuid not in Service._active_servers

        finally:
            Service._active_servers = original_servers

    @patch("mindtrace.services.core.service.psutil.Process")
    def test_cleanup_server_parent_wait_no_such_process(self, mock_psutil_process):
        """Test _cleanup_server with parent wait NoSuchProcess exception."""
        # Setup mock process
        mock_process = Mock()
        mock_process.pid = 1234

        # Setup psutil mock
        mock_parent = Mock()
        mock_parent.children.return_value = []  # No children
        mock_parent.terminate.return_value = None
        # Make parent.wait() raise NoSuchProcess
        mock_parent.wait.side_effect = psutil.NoSuchProcess(1234)
        mock_psutil_process.return_value = mock_parent

        # Setup active servers
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        original_servers = Service._active_servers.copy()
        Service._active_servers[test_uuid] = mock_process

        try:
            # Should handle NoSuchProcess exception gracefully
            Service._cleanup_server(test_uuid)

            # Should call both terminate and wait
            mock_parent.terminate.assert_called_once()
            mock_parent.wait.assert_called_once_with(timeout=5)
            # Should still remove from active servers
            assert test_uuid not in Service._active_servers

        finally:
            Service._active_servers = original_servers

    def test_cleanup_all_servers(self):
        """Test _cleanup_all_servers method."""
        # Setup multiple mock servers
        test_uuid1 = UUID("12345678-1234-5678-1234-567812345678")
        test_uuid2 = UUID("87654321-4321-8765-4321-876543218765")
        mock_process1 = Mock()
        mock_process2 = Mock()

        original_servers = Service._active_servers.copy()
        Service._active_servers = {test_uuid1: mock_process1, test_uuid2: mock_process2}

        try:
            with patch.object(Service, "_cleanup_server") as mock_cleanup_server:
                # Call cleanup all servers
                Service._cleanup_all_servers()

                # Should call _cleanup_server for each active server
                assert mock_cleanup_server.call_count == 2
                mock_cleanup_server.assert_any_call(test_uuid1)
                mock_cleanup_server.assert_any_call(test_uuid2)

        finally:
            Service._active_servers = original_servers


class TestServiceGlobalEndpointPollution:
    """Test for global endpoint pollution due to class-level _endpoints."""

    def test_no_global_endpoint_pollution(self):
        from mindtrace.services.core.utils import generate_connection_manager
        from mindtrace.services.samples.echo_service import EchoService

        # Ensure clean state
        if hasattr(Service, "_endpoints"):
            Service._endpoints.clear()
        if hasattr(EchoService, "_endpoints"):
            EchoService._endpoints.clear()

        # Create EchoService instance
        echo_service = EchoService()
        echo_endpoints = list(echo_service._endpoints.keys())
        # Should contain 'echo' and system endpoints
        assert "echo" in echo_endpoints
        # Create a regular Service instance
        regular_service = Service()
        service_endpoints = list(regular_service._endpoints.keys())
        # Should NOT contain 'echo'
        assert "echo" not in service_endpoints, (
            f"Global pollution detected: Service._endpoints contains: {service_endpoints}"
        )

        # Generate connection managers
        EchoCM = generate_connection_manager(EchoService)
        ServiceCM = generate_connection_manager(Service)
        echo_methods = [attr for attr in dir(EchoCM) if not attr.startswith("_") and callable(getattr(EchoCM, attr))]
        service_methods = [
            attr for attr in dir(ServiceCM) if not attr.startswith("_") and callable(getattr(ServiceCM, attr))
        ]
        # EchoCM should have 'echo', ServiceCM should NOT
        assert "echo" in echo_methods
        assert "echo" not in service_methods, (
            f"Global pollution detected: Service connection manager has methods: {service_methods}"
        )


class TestServiceInterruption:
    """Test Service interruption handling during launch."""

    def test_connect_with_interrupt_handling_process_exited_cleanly(self):
        """Test _connect_with_interrupt_handling when process exits cleanly."""
        mock_process = Mock()
        mock_process.poll.return_value = 0  # Process has exited
        mock_process.returncode = 0  # Clean exit

        with pytest.raises(SystemExit, match="Service exited cleanly."):
            Service._connect_with_interrupt_handling("http://localhost:8000", mock_process, 30)

    def test_connect_with_interrupt_handling_process_error_exit(self):
        """Test _connect_with_interrupt_handling when process exits with error."""
        mock_process = Mock()
        mock_process.poll.return_value = 0  # Process has exited
        mock_process.returncode = 1  # Error exit

        with pytest.raises(RuntimeError, match="Server exited with code 1"):
            Service._connect_with_interrupt_handling("http://localhost:8000", mock_process, 30)

    def test_connect_with_interrupt_handling_process_sigint(self):
        """Test _connect_with_interrupt_handling when process terminated by SIGINT."""
        import signal

        mock_process = Mock()
        mock_process.poll.return_value = 0  # Process has exited
        mock_process.returncode = -signal.SIGINT  # Terminated by SIGINT

        with pytest.raises(KeyboardInterrupt, match="Service terminated by SIGINT"):
            Service._connect_with_interrupt_handling("http://localhost:8000", mock_process, 30)

    def test_connect_with_interrupt_handling_process_running(self):
        """Test _connect_with_interrupt_handling when process is still running."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process is still running

        with patch.object(Service, "connect") as mock_connect:
            mock_connection_manager = Mock()
            mock_connect.return_value = mock_connection_manager

            result = Service._connect_with_interrupt_handling("http://localhost:8000", mock_process, 30)

            assert result == mock_connection_manager
            mock_connect.assert_called_once_with(url="http://localhost:8000")

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_keyboard_interrupt_during_wait_for_launch(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host
    ):
        """Test launch method KeyboardInterrupt during wait_for_launch."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            # Mock the timeout handler to raise KeyboardInterrupt
            mock_timeout_handler = Mock()
            mock_timeout_handler.run.side_effect = KeyboardInterrupt("User interrupted")

            with patch("mindtrace.services.core.service.Timeout", return_value=mock_timeout_handler):
                with patch.object(Service, "_cleanup_server") as mock_cleanup:
                    with patch("mindtrace.services.core.service.logging.getLogger") as mock_get_logger:
                        mock_logger = Mock()
                        mock_get_logger.return_value = mock_logger

                        with pytest.raises(KeyboardInterrupt, match="User interrupted"):
                            Service.launch(wait_for_launch=True, timeout=30)

                        # Should cleanup the server
                        mock_cleanup.assert_called_with(test_uuid)

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_system_exit_during_wait_for_launch(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host
    ):
        """Test launch method SystemExit during wait_for_launch."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            # Mock the timeout handler to raise SystemExit
            mock_timeout_handler = Mock()
            mock_timeout_handler.run.side_effect = SystemExit("Service terminated")

            with patch("mindtrace.services.core.service.Timeout", return_value=mock_timeout_handler):
                with patch.object(Service, "_cleanup_server") as mock_cleanup:
                    with patch("mindtrace.services.core.service.logging.getLogger") as mock_get_logger:
                        mock_logger = Mock()
                        mock_get_logger.return_value = mock_logger

                        with pytest.raises(SystemExit, match="Service terminated"):
                            Service.launch(wait_for_launch=True, timeout=30)

                        # Should cleanup the server
                        mock_cleanup.assert_called_with(test_uuid)

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_general_exception_during_wait_for_launch(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host
    ):
        """Test launch method general exception during wait_for_launch."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            # Mock the timeout handler to raise a general exception
            mock_timeout_handler = Mock()
            test_exception = RuntimeError("Connection timeout")
            mock_timeout_handler.run.side_effect = test_exception

            with patch("mindtrace.services.core.service.Timeout", return_value=mock_timeout_handler):
                with patch.object(Service, "_cleanup_server") as mock_cleanup:
                    with pytest.raises(RuntimeError, match="Connection timeout"):
                        Service.launch(wait_for_launch=True, timeout=30)

                    # Should cleanup the server
                    mock_cleanup.assert_called_with(test_uuid)

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_successful_wait_for_launch(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host
    ):
        """Test launch method successful wait_for_launch."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            # Mock the timeout handler to return a connection manager
            mock_timeout_handler = Mock()
            mock_connection_manager = Mock()
            mock_timeout_handler.run.return_value = mock_connection_manager

            with patch("mindtrace.services.core.service.Timeout", return_value=mock_timeout_handler):
                result = Service.launch(wait_for_launch=True, timeout=30)

                # Should return the connection manager
                assert result == mock_connection_manager
                # Should call timeout handler with correct parameters
                mock_timeout_handler.run.assert_called_once()
                call_args = mock_timeout_handler.run.call_args
                assert call_args[0][0] == Service._connect_with_interrupt_handling
                assert call_args[1]["process"] == mock_process
                assert call_args[1]["timeout"] == 30

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_timeout_handler_configuration(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host, monkeypatch
    ):
        """Test launch method timeout handler configuration."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            # Ensure SERVICE host matches expected in assertion
            monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://service.example.com:8080")
            from mindtrace.core import CoreConfig

            Service.config = CoreConfig()

            with patch("mindtrace.services.core.service.Timeout") as mock_timeout_class:
                mock_timeout_instance = Mock()
                mock_timeout_class.return_value = mock_timeout_instance
                mock_connection_manager = Mock()
                mock_timeout_instance.run.return_value = mock_connection_manager

                Service.launch(wait_for_launch=True, timeout=60, progress_bar=True)

                # Should create Timeout with correct parameters
                mock_timeout_class.assert_called_once_with(
                    timeout=60,
                    exceptions=(ConnectionRefusedError, requests.exceptions.ConnectionError, HTTPException),
                    progress_bar=True,
                    desc=f"Launching {Service.unique_name.split('.')[-1]} at http://service.example.com:8080",
                )

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_no_wait_for_launch_returns_none(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host
    ):
        """Test launch method when wait_for_launch=False returns None."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            result = Service.launch(wait_for_launch=False)

            # Should return None when wait_for_launch=False
            assert result is None

        finally:
            # Restore original state
            Service._active_servers = original_servers

    @patch.object(Service, "status_at_host")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_signal_valueerror_handling(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_status_at_host
    ):
        """Test launch method handles ValueError from signal.signal."""
        # Setup mocks
        mock_status_at_host.return_value = ServerStatus.DOWN
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        mock_uuid.return_value = test_uuid

        # Mock process
        mock_process = Mock()
        mock_popen.return_value = mock_process

        # Make signal.signal raise ValueError (e.g., when called from non-main thread)
        mock_signal.side_effect = ValueError("signal only works in main thread")

        # Clear any existing active servers
        original_servers = Service._active_servers.copy()
        Service._active_servers.clear()

        try:
            # Should not raise, but log a warning
            # Patch logger.warning directly since logger is a property
            original_logger = Service.logger
            mock_logger = Mock()
            mock_logger.warning = Mock()
            Service.logger = mock_logger

            try:
                result = Service.launch(wait_for_launch=False)

                # Should still work and return None
                assert result is None
                # Should log warning about signal handler registration failure
                mock_logger.warning.assert_called()
                warning_call = str(mock_logger.warning.call_args)
                assert "Could not register signal handlers" in warning_call
                assert "normal if you launch a Service from another Service" in warning_call
            finally:
                Service.logger = original_logger

        finally:
            # Restore original state
            Service._active_servers = original_servers
