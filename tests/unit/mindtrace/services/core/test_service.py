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
            service.add_endpoint("dummy", dummy_handler)


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

        with patch.object(Service, "config", {"MINDTRACE_SERVER_PIDS_DIR_PATH": "/tmp/pids"}):
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
        assert "Heartbeat check successful" in heartbeat.message
        assert heartbeat.details is None


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

    @patch.object(Service, "config", {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://service.example.com:8080"}})
    def test_default_url_service_specific(self):
        """Test default_url returns service-specific URL from config."""
        result = Service.default_url()

        assert str(result) == "http://service.example.com:8080"

    @patch.object(Service, "config", {"MINDTRACE_DEFAULT_HOST_URLS": {"ServerBase": "http://base.example.com:8080"}})
    def test_default_url_server_base(self):
        """Test default_url returns ServerBase URL when service-specific not found."""
        result = Service.default_url()

        assert str(result) == "http://base.example.com:8080"

    @patch.object(Service, "config", {"MINDTRACE_DEFAULT_HOST_URLS": {}})
    def test_default_url_fallback(self):
        """Test default_url returns fallback URL when no config found."""
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

    @patch.object(Service, "config", {"MINDTRACE_DEFAULT_LOG_DIR": "/tmp/logs"})
    def test_default_log_file(self):
        """Test default_log_file method."""
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
        """Test FastAPI lifespan context manager (covers lines 98-101)."""
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
        """Test launch method RuntimeError handling (covers lines 234-240)."""
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
        """Test launch method HTTPException when service already running (covers line 234)."""
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
        """Test launch method blocking with KeyboardInterrupt (covers lines 290-299)."""
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
    @patch.object(Service, "build_url")
    @patch("mindtrace.services.core.service.subprocess.Popen")
    @patch("mindtrace.services.core.service.uuid.uuid1")
    @patch("mindtrace.services.core.service.atexit.register")
    @patch("mindtrace.services.core.service.signal.signal")
    def test_launch_blocking_finally_cleanup(
        self, mock_signal, mock_atexit, mock_uuid, mock_popen, mock_build_url, mock_status_at_host
    ):
        """Test launch method blocking finally block (covers lines 290-299)."""
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
        """Test _cleanup_server with child NoSuchProcess exception (covers lines 328-331)."""
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
        """Test _cleanup_server with parent NoSuchProcess exception (covers lines 335-338)."""
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
        """Test _cleanup_server with parent terminate NoSuchProcess exception (covers lines 335-336)."""
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
        """Test _cleanup_server with parent wait NoSuchProcess exception (covers lines 335-336)."""
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
        """Test _cleanup_all_servers method (covers lines 345-346)."""
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
