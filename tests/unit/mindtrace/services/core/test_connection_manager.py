"""Unit tests for the ConnectionManager class."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
import pytest
import requests
from fastapi import HTTPException
from urllib3.util.url import parse_url

from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.types import ServerStatus, ShutdownOutput, StatusOutput


class TestConnectionManagerInitialization:
    """Test ConnectionManager initialization and configuration."""

    def test_init_with_default_url(self):
        """Test initialization with default URL from config."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            cm = ConnectionManager()
            assert str(cm.url) == "http://localhost:8000"
            assert cm._server_id is None
            assert cm._server_pid_file is None

    def test_init_with_custom_url(self):
        """Test initialization with custom URL."""
        custom_url = parse_url("http://custom.host:9000")
        cm = ConnectionManager(url=custom_url)
        assert cm.url == custom_url
        assert str(cm.url) == "http://custom.host:9000"

    def test_init_with_server_id_and_pid_file(self):
        """Test initialization with server ID and PID file."""
        server_id = uuid4()
        pid_file = "/tmp/server.pid"
        
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            cm = ConnectionManager(server_id=server_id, server_pid_file=pid_file)
            assert cm._server_id == server_id
            assert cm._server_pid_file == pid_file

    def test_init_inherits_from_mindtrace(self):
        """Test that ConnectionManager properly inherits from Mindtrace."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            cm = ConnectionManager()
            assert hasattr(cm, 'logger')
            assert hasattr(cm, 'config')
            assert hasattr(cm, 'name')


class TestConnectionManagerShutdown:
    """Test the shutdown functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            self.cm = ConnectionManager()

    @patch('mindtrace.services.core.connection_manager.requests.request')
    def test_shutdown_non_blocking_success(self, mock_request):
        """Test successful non-blocking shutdown."""
        # Mock successful shutdown response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        result = self.cm.shutdown(block=False)

        # Verify the request was made correctly
        mock_request.assert_called_once_with(
            "POST", 
            "http://localhost:8000/shutdown", 
            timeout=60
        )
        
        # Verify the result
        assert isinstance(result, ShutdownOutput)
        assert result.shutdown is True

    @patch('mindtrace.services.core.connection_manager.requests.request')
    def test_shutdown_request_failure(self, mock_request):
        """Test shutdown when the shutdown request fails."""
        # Mock failed shutdown response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.content = b"Internal Server Error"
        mock_request.return_value = mock_response

        with pytest.raises(HTTPException):
            self.cm.shutdown(block=False)

        mock_request.assert_called_once()

    @patch('mindtrace.services.core.connection_manager.Timeout')
    @patch('mindtrace.services.core.connection_manager.requests.request')
    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_shutdown_blocking_success(self, mock_post, mock_request, mock_timeout):
        """Test successful blocking shutdown."""
        # Mock successful shutdown response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        # Mock the timeout handler to simulate successful server shutdown check
        mock_timeout_instance = Mock()
        mock_timeout.return_value = mock_timeout_instance
        mock_timeout_instance.run.return_value = True

        result = self.cm.shutdown(block=True)

        # Verify shutdown request was made
        mock_request.assert_called_once_with(
            "POST", 
            "http://localhost:8000/shutdown", 
            timeout=60
        )
        
        # Verify timeout was configured correctly
        mock_timeout.assert_called_once_with(
            timeout=30,
            retry_delay=0.2,
            exceptions=(ConnectionError,),
            progress_bar=False
        )
        
        # Verify timeout.run was called
        mock_timeout_instance.run.assert_called_once()
        
        assert isinstance(result, ShutdownOutput)
        assert result.shutdown is True

    @patch('mindtrace.services.core.connection_manager.Timeout')
    @patch('mindtrace.services.core.connection_manager.requests.request')
    def test_shutdown_blocking_timeout(self, mock_request, mock_timeout):
        """Test blocking shutdown when server doesn't shut down in time."""
        # Mock successful shutdown response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        # Mock timeout to raise TimeoutError
        mock_timeout_instance = Mock()
        mock_timeout.return_value = mock_timeout_instance
        mock_timeout_instance.run.side_effect = TimeoutError("Timeout occurred")

        with pytest.raises(TimeoutError, match="Server at http://localhost:8000 did not shut down"):
            self.cm.shutdown(block=True)

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_check_server_down_connection_error(self, mock_post):
        """Test the internal check_server_down function with connection error."""
        # Mock successful shutdown response first
        with patch('mindtrace.services.core.connection_manager.requests.request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            # Mock post to raise ConnectionError (server is down)
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

            # Mock timeout to call the check function once and succeed
            with patch('mindtrace.services.core.connection_manager.Timeout') as mock_timeout:
                mock_timeout_instance = Mock()
                mock_timeout.return_value = mock_timeout_instance
                
                # Simulate timeout.run calling the check function
                def simulate_check_call(check_func):
                    return check_func()  # This should return True when ConnectionError is raised
                
                mock_timeout_instance.run.side_effect = simulate_check_call

                result = self.cm.shutdown(block=True)
                assert result.shutdown is True

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_check_server_down_timeout_error(self, mock_post):
        """Test the internal check_server_down function with timeout error."""
        with patch('mindtrace.services.core.connection_manager.requests.request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            # Mock post to raise Timeout (server is shutting down)
            mock_post.side_effect = requests.exceptions.Timeout("Request timeout")

            with patch('mindtrace.services.core.connection_manager.Timeout') as mock_timeout:
                mock_timeout_instance = Mock()
                mock_timeout.return_value = mock_timeout_instance
                
                def simulate_check_call(check_func):
                    return check_func()
                
                mock_timeout_instance.run.side_effect = simulate_check_call

                result = self.cm.shutdown(block=True)
                assert result.shutdown is True

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_check_server_down_server_still_responding(self, mock_post):
        """Test the internal check_server_down function when server is still responding (line 65)."""
        # Mock successful shutdown response first
        with patch('mindtrace.services.core.connection_manager.requests.request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            # Mock post to return a successful response (server still responding)
            status_response = Mock()
            status_response.status_code = 200
            mock_post.return_value = status_response

            # Mock timeout to call the check function and verify ConnectionError is raised
            with patch('mindtrace.services.core.connection_manager.Timeout') as mock_timeout:
                mock_timeout_instance = Mock()
                mock_timeout.return_value = mock_timeout_instance
                
                # Track whether we've verified the ConnectionError from line 65
                connection_error_verified = False
                
                # Simulate timeout.run calling the check function multiple times
                def simulate_check_call(check_func):
                    nonlocal connection_error_verified
                    # This should raise ConnectionError("Server still responding") from line 65
                    try:
                        result = check_func()
                        # If check_func returns without exception, that's unexpected in this test
                        pytest.fail("Expected ConnectionError('Server still responding') to be raised")
                    except ConnectionError as e:
                        # Verify the specific error message from line 65
                        assert str(e) == "Server still responding"
                        connection_error_verified = True
                        # Re-raise to simulate the timeout handler catching it for retry
                        raise
                
                mock_timeout_instance.run.side_effect = simulate_check_call

                # The timeout handler should catch the ConnectionError and retry until timeout
                with pytest.raises(ConnectionError, match="Server still responding"):
                    self.cm.shutdown(block=True)

                # Verify the status check was made and the ConnectionError was verified
                mock_post.assert_called_with("http://localhost:8000/status", timeout=2)
                assert connection_error_verified, "ConnectionError from line 65 was not properly verified"


class TestConnectionManagerAsyncShutdown:
    """Test the async shutdown functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            self.cm = ConnectionManager()

    @pytest.mark.asyncio
    async def test_ashutdown_calls_sync_shutdown(self):
        """Test that ashutdown properly calls the sync shutdown method."""
        with patch.object(self.cm, 'shutdown') as mock_shutdown:
            mock_shutdown.return_value = ShutdownOutput(shutdown=True)
            
            result = await self.cm.ashutdown(block=False)
            
            mock_shutdown.assert_called_once_with(False)
            assert isinstance(result, ShutdownOutput)
            assert result.shutdown is True

    @pytest.mark.asyncio
    async def test_ashutdown_with_blocking(self):
        """Test async shutdown with blocking enabled."""
        with patch.object(self.cm, 'shutdown') as mock_shutdown:
            mock_shutdown.return_value = ShutdownOutput(shutdown=True)
            
            result = await self.cm.ashutdown(block=True)
            
            mock_shutdown.assert_called_once_with(True)
            assert result.shutdown is True


class TestConnectionManagerStatus:
    """Test the status functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            self.cm = ConnectionManager()

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_status_success(self, mock_post):
        """Test successful status request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": ServerStatus.AVAILABLE,
            "server_id": str(uuid4()),
            "uptime": 123.45
        }
        mock_post.return_value = mock_response

        result = self.cm.status()

        mock_post.assert_called_once_with(
            "http://localhost:8000/status",
            timeout=10
        )
        
        assert isinstance(result, StatusOutput)
        assert result.status == ServerStatus.AVAILABLE

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_status_server_error(self, mock_post):
        """Test status request when server returns error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        result = self.cm.status()

        assert isinstance(result, StatusOutput)
        assert result.status == ServerStatus.DOWN

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_status_connection_error(self, mock_post):
        """Test status request when connection fails."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        result = self.cm.status()

        assert isinstance(result, StatusOutput)
        assert result.status == ServerStatus.DOWN

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_status_timeout_error(self, mock_post):
        """Test status request when request times out."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timeout")

        result = self.cm.status()

        assert isinstance(result, StatusOutput)
        assert result.status == ServerStatus.DOWN

    @patch('mindtrace.services.core.connection_manager.requests.post')
    def test_status_general_request_error(self, mock_post):
        """Test status request with general request exception."""
        mock_post.side_effect = requests.exceptions.RequestException("General error")

        result = self.cm.status()

        assert isinstance(result, StatusOutput)
        assert result.status == ServerStatus.DOWN


class TestConnectionManagerAsyncStatus:
    """Test the async status functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            self.cm = ConnectionManager()

    @pytest.mark.asyncio
    async def test_astatus_success(self):
        """Test successful async status request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": ServerStatus.AVAILABLE,
            "server_id": str(uuid4()),
            "uptime": 123.45
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await self.cm.astatus()

            mock_client.post.assert_called_once_with("http://localhost:8000/status")
            assert isinstance(result, StatusOutput)
            assert result.status == ServerStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_astatus_server_error(self):
        """Test async status when server returns error."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await self.cm.astatus()

            assert isinstance(result, StatusOutput)
            assert result.status == ServerStatus.DOWN

    @pytest.mark.asyncio
    async def test_astatus_connection_error(self):
        """Test async status when connection fails."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")

            result = await self.cm.astatus()

            assert isinstance(result, StatusOutput)
            assert result.status == ServerStatus.DOWN

    @pytest.mark.asyncio
    async def test_astatus_timeout_error(self):
        """Test async status when request times out."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.TimeoutException("Request timeout")

            result = await self.cm.astatus()

            assert isinstance(result, StatusOutput)
            assert result.status == ServerStatus.DOWN

    @pytest.mark.asyncio
    async def test_astatus_general_request_error(self):
        """Test async status with general request exception."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.RequestError("General error")

            result = await self.cm.astatus()

            assert isinstance(result, StatusOutput)
            assert result.status == ServerStatus.DOWN


class TestConnectionManagerContextManager:
    """Test the context manager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            self.cm = ConnectionManager()

    def test_exit_calls_shutdown(self):
        """Test that __exit__ calls shutdown method."""
        with patch.object(self.cm, 'shutdown') as mock_shutdown:
            mock_shutdown.return_value = ShutdownOutput(shutdown=True)
            
            # Simulate normal exit (no exception)
            result = self.cm.__exit__(None, None, None)
            
            mock_shutdown.assert_called_once()
            assert result is False

    def test_exit_with_exception_calls_shutdown_and_logs(self):
        """Test that __exit__ handles exceptions properly."""
        with patch.object(self.cm, 'shutdown') as mock_shutdown, \
             patch.object(self.cm.logger, 'exception') as mock_log_exception:
            
            mock_shutdown.return_value = ShutdownOutput(shutdown=True)
            self.cm.suppress = False  # Default suppress behavior
            
            # Simulate exit with exception
            exc_type = ValueError
            exc_val = ValueError("Test error")
            exc_tb = None
            
            result = self.cm.__exit__(exc_type, exc_val, exc_tb)
            
            mock_shutdown.assert_called_once()
            mock_log_exception.assert_called_once_with(
                "Exception occurred", 
                exc_info=(exc_type, exc_val, exc_tb)
            )
            assert result == self.cm.suppress

    def test_exit_shutdown_fails_still_handles_exception(self):
        """Test that __exit__ handles exceptions even if shutdown fails."""
        with patch.object(self.cm, 'shutdown') as mock_shutdown, \
             patch.object(self.cm.logger, 'exception') as mock_log_exception:
            
            # Make shutdown raise an exception
            mock_shutdown.side_effect = Exception("Shutdown failed")
            self.cm.suppress = True
            
            exc_type = ValueError
            exc_val = ValueError("Test error")
            exc_tb = None
            
            result = self.cm.__exit__(exc_type, exc_val, exc_tb)
            
            mock_shutdown.assert_called_once()
            mock_log_exception.assert_called_once_with(
                "Exception occurred", 
                exc_info=(exc_type, exc_val, exc_tb)
            )
            assert result == self.cm.suppress


class TestConnectionManagerIntegration:
    """Integration-style tests for ConnectionManager workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            self.cm = ConnectionManager()

    @patch('mindtrace.services.core.connection_manager.requests.post')
    @patch('mindtrace.services.core.connection_manager.requests.request')
    def test_status_then_shutdown_workflow(self, mock_request, mock_post):
        """Test a typical workflow: check status, then shutdown."""
        # Mock status response - server is available
        status_response = Mock()
        status_response.status_code = 200
        status_response.json.return_value = {
            "status": ServerStatus.AVAILABLE,
            "server_id": str(uuid4())
        }
        mock_post.return_value = status_response

        # Mock shutdown response
        shutdown_response = Mock()
        shutdown_response.status_code = 200
        mock_request.return_value = shutdown_response

        # Check status first
        status = self.cm.status()
        assert status.status == ServerStatus.AVAILABLE

        # Then shutdown
        result = self.cm.shutdown(block=False)
        assert result.shutdown is True

        # Verify both calls were made
        mock_post.assert_called_once()
        mock_request.assert_called_once()

    def test_context_manager_usage(self):
        """Test using ConnectionManager as a context manager."""
        with patch.object(ConnectionManager, 'config', {"MINDTRACE_DEFAULT_HOST_URLS": {"Service": "http://localhost:8000"}}):
            with patch('mindtrace.services.core.connection_manager.requests.request') as mock_request:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_request.return_value = mock_response

                with ConnectionManager() as cm:
                    assert isinstance(cm, ConnectionManager)
                    # Context manager should work normally
                    pass
                
                # Shutdown should be called on exit
                mock_request.assert_called_once_with(
                    "POST", 
                    "http://localhost:8000/shutdown", 
                    timeout=60
                )
