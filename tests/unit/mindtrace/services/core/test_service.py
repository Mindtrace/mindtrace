import pytest
from unittest.mock import Mock, patch, AsyncMock
from pydantic import BaseModel
from fastapi import HTTPException

from mindtrace.core import TaskSchema
from mindtrace.services import Service, generate_connection_manager


class TestInput(BaseModel):
    message: str
    count: int = 1


class TestOutput(BaseModel):
    result: str
    processed_count: int


class TestService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add a test task
        test_task = TaskSchema(
            name="test_task",
            input_schema=TestInput,
            output_schema=TestOutput,
        )
        self.add_endpoint("test_task", self.test_handler, schema=test_task)
        
        # Add another task for multiple task testing
        echo_task = TaskSchema(
            name="echo",
            input_schema=TestInput,
            output_schema=TestOutput,
        )
        self.add_endpoint("echo", self.echo_handler, schema=echo_task)

    def test_handler(self, payload: TestInput) -> TestOutput:
        return TestOutput(
            result=f"Processed: {payload.message}",
            processed_count=payload.count * 2
        )
    
    def echo_handler(self, payload: TestInput) -> TestOutput:
        return TestOutput(
            result=payload.message,
            processed_count=payload.count
        )


class TestServiceClass:
    """Test the Service class functionality"""
    
    def test_service_initialization(self):
        service = TestService()
        # Check that our custom endpoints are present (plus system endpoints)
        assert "test_task" in service.endpoints
        assert "echo" in service.endpoints
        # Verify system endpoints are also present
        assert "status" in service.endpoints
        assert "heartbeat" in service.endpoints
    
    def test_task_schema_registration(self):
        service = TestService()
        
        # Check test_task
        test_task = service.endpoints["test_task"]
        assert test_task.name == "test_task"
        assert test_task.input_schema == TestInput
        assert test_task.output_schema == TestOutput
        
        # Check echo task
        echo_task = service.endpoints["echo"]
        assert echo_task.name == "echo"
        assert echo_task.input_schema == TestInput
        assert echo_task.output_schema == TestOutput
    
    def test_add_endpoint_without_task(self):
        service = Service()
        
        def dummy_handler():
            return {"status": "ok"}
        
        # The schema parameter is now required, so this should raise TypeError
        with pytest.raises(TypeError):
            service.add_endpoint("dummy", dummy_handler)


class TestGenerateConnectionManager:
    """Test the generate_connection_manager function"""
    
    def test_connection_manager_generation(self):
        """Test that connection manager is generated with correct methods"""
        ConnectionManager = generate_connection_manager(TestService)
        
        # Check class name
        assert ConnectionManager.__name__ == "TestServiceConnectionManager"
        
        # Check that methods exist
        manager_instance = Mock()
        manager_instance.__class__ = ConnectionManager
        
        # Sync methods
        assert hasattr(ConnectionManager, "test_task")
        assert hasattr(ConnectionManager, "echo")
        assert hasattr(ConnectionManager, "get_job")
        
        # Async methods
        assert hasattr(ConnectionManager, "atest_task")
        assert hasattr(ConnectionManager, "aecho")
        assert hasattr(ConnectionManager, "aget_job")
    
    def test_method_names_and_docs(self):
        """Test that generated methods have correct names and documentation"""
        ConnectionManager = generate_connection_manager(TestService)
        
        # Test sync method
        test_method = getattr(ConnectionManager, "test_task")
        assert test_method.__name__ == "test_task"
        assert "test_task" in test_method.__doc__
        assert "/test_task" in test_method.__doc__
        
        # Test async method
        atest_method = getattr(ConnectionManager, "atest_task")
        assert atest_method.__name__ == "atest_task"
        assert "Async version" in atest_method.__doc__
        assert "test_task" in atest_method.__doc__


class TestSyncMethods:
    """Test synchronous method functionality"""
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_sync_method_success(self, mock_post):
        """Test successful sync method call"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "Processed: test message",
            "processed_count": 2
        }
        mock_post.return_value = mock_response
        
        # Create connection manager and instance
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Call the method
        result = ConnectionManager.test_task(manager, message="test message", count=1)
        
        # Verify the call
        mock_post.assert_called_once_with(
            "http://localhost:8000/test_task",
            json={"message": "test message", "count": 1},
            params={"validate_output": "true"},
            timeout=30
        )
        
        # Verify the result
        assert isinstance(result, TestOutput)
        assert result.result == "Processed: test message"
        assert result.processed_count == 2
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_sync_method_non_validating(self, mock_post):
        """Test non-validating sync method call"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "123", "status": "pending"}
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Call without output validation
        result = ConnectionManager.test_task(manager, validate_output=False, message="test", count=1)
        
        # Verify parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["params"]["validate_output"] == "false"
        
        # Should return raw result, not parsed as TestOutput
        assert result == {"job_id": "123", "status": "pending"}
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_sync_method_error(self, mock_post):
        """Test sync method error handling"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            ConnectionManager.test_task(manager, message="test", count=1)
        
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"
    
    @patch('mindtrace.services.base.utils.httpx.get')
    def test_get_job_success(self, mock_get):
        """Test get_job method success"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "123", "status": "completed", "result": "done"}
        mock_get.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        result = ConnectionManager.get_job(manager, "123")
        
        mock_get.assert_called_once_with("http://localhost:8000/job/123", timeout=10)
        assert result == {"job_id": "123", "status": "completed", "result": "done"}
    
    @patch('mindtrace.services.base.utils.httpx.get')
    def test_get_job_not_found(self, mock_get):
        """Test get_job method when job not found"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        result = ConnectionManager.get_job(manager, "nonexistent")
        
        assert result is None


class TestAsyncMethods:
    """Test asynchronous method functionality"""
    
    @pytest.mark.asyncio
    @patch('mindtrace.services.base.utils.httpx.AsyncClient')
    async def test_async_method_success(self, mock_client_class):
        """Test successful async method call"""
        # Setup mock async client
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "Processed: async test",
            "processed_count": 4
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Create connection manager and instance
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Call the async method
        result = await ConnectionManager.atest_task(manager, message="async test", count=2)
        
        # Verify the async call
        mock_client.post.assert_called_once_with(
            "http://localhost:8000/test_task",
            json={"message": "async test", "count": 2},
            params={"validate_output": "true"}
        )
        
        # Verify the result
        assert isinstance(result, TestOutput)
        assert result.result == "Processed: async test"
        assert result.processed_count == 4
    
    @pytest.mark.asyncio
    @patch('mindtrace.services.base.utils.httpx.AsyncClient')
    async def test_async_method_error(self, mock_client_class):
        """Test async method error handling"""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await ConnectionManager.atest_task(manager, message="test", count=1)
        
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Bad Request"
    
    @pytest.mark.asyncio
    @patch('mindtrace.services.base.utils.httpx.AsyncClient')
    async def test_aget_job_success(self, mock_client_class):
        """Test async get_job method"""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "456", "status": "running"}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        result = await ConnectionManager.aget_job(manager, "456")
        
        mock_client.get.assert_called_once_with("http://localhost:8000/job/456")
        assert result == {"job_id": "456", "status": "running"}
    
    @pytest.mark.asyncio
    @patch('mindtrace.services.base.utils.httpx.AsyncClient')
    async def test_aget_job_not_found(self, mock_client_class):
        """Test async get_job method when job not found"""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        result = await ConnectionManager.aget_job(manager, "nonexistent")
        
        assert result is None


class TestInputValidation:
    """Test input validation through Pydantic schemas"""
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_input_validation_success(self, mock_post):
        """Test that input validation works correctly"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test", "processed_count": 1}
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Valid input
        ConnectionManager.test_task(manager, message="test", count=5)
        
        # Check that the payload was properly validated and serialized
        call_args = mock_post.call_args
        expected_payload = {"message": "test", "count": 5}
        assert call_args[1]["json"] == expected_payload
    
    def test_input_validation_error(self):
        """Test that input validation raises appropriate errors"""
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Missing required field should raise validation error
        with pytest.raises(Exception):  # Pydantic validation error
            ConnectionManager.test_task(manager, count=5)  # missing 'message'


class TestMultipleTasks:
    """Test handling of services with multiple tasks"""
    
    def test_multiple_tasks_registered(self):
        """Test that multiple tasks are properly registered"""
        ConnectionManager = generate_connection_manager(TestService)
        
        # Both tasks should be available
        assert hasattr(ConnectionManager, "test_task")
        assert hasattr(ConnectionManager, "echo")
        assert hasattr(ConnectionManager, "atest_task")
        assert hasattr(ConnectionManager, "aecho")
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_different_tasks_different_endpoints(self, mock_post):
        """Test that different tasks call different endpoints"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test", "processed_count": 1}
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8000"
        manager.__class__ = ConnectionManager
        
        # Call test_task
        ConnectionManager.test_task(manager, message="test1", count=1)
        first_call = mock_post.call_args
        
        mock_post.reset_mock()
        
        # Call echo
        ConnectionManager.echo(manager, message="test2", count=2)
        second_call = mock_post.call_args
        
        # Should call different endpoints
        assert first_call[0][0] == "http://localhost:8000/test_task"
        assert second_call[0][0] == "http://localhost:8000/echo"
        
        # Should have different payloads
        assert first_call[1]["json"]["message"] == "test1"
        assert second_call[1]["json"]["message"] == "test2"


class TestUrlConstruction:
    """Test URL construction and the fix for double slash issues"""
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_url_construction_with_trailing_slash(self, mock_post):
        """Test URL construction with trailing slash in base URL"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test", "processed_count": 1}
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8080/"  # with trailing slash
        manager.__class__ = ConnectionManager
        
        ConnectionManager.test_task(manager, message="test", count=1)
        
        # Should strip trailing slash to avoid double slash
        called_url = mock_post.call_args[0][0]
        assert called_url == "http://localhost:8080/test_task"
        assert "//" not in called_url.replace("://", "")
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_url_construction_without_trailing_slash(self, mock_post):
        """Test URL construction without trailing slash in base URL"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test", "processed_count": 1}
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        manager = Mock()
        manager.url = "http://localhost:8080"  # without trailing slash
        manager.__class__ = ConnectionManager
        
        ConnectionManager.test_task(manager, message="test", count=1)
        
        # Should work correctly with no trailing slash
        called_url = mock_post.call_args[0][0]
        assert called_url == "http://localhost:8080/test_task"
    
    @patch('mindtrace.services.base.utils.httpx.post')
    def test_url_construction_various_formats(self, mock_post):
        """Test URL construction with various URL formats"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test", "processed_count": 1}
        mock_post.return_value = mock_response
        
        ConnectionManager = generate_connection_manager(TestService)
        
        test_urls = [
            "http://localhost:8080/",
            "http://localhost:8080",
            "https://example.com/",
            "https://example.com",
            "http://192.168.1.1:3000/",
            "http://192.168.1.1:3000",
        ]
        
        for url in test_urls:
            mock_post.reset_mock()
            
            manager = Mock()
            manager.url = url
            manager.__class__ = ConnectionManager
            
            ConnectionManager.test_task(manager, message="test", count=1)
            
            # Extract the URL that was called
            called_url = mock_post.call_args[0][0]
            
            # Should always result in single slash between host and path
            expected_base = url.rstrip('/')
            expected_url = f"{expected_base}/test_task"
            
            assert called_url == expected_url, f"URL {url} resulted in {called_url}, expected {expected_url}"
            # Ensure no double slashes (excluding protocol://)
            assert "//" not in called_url.replace("://", ""), f"Double slash found in {called_url}"



