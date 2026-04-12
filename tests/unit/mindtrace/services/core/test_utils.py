from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from urllib3.util.url import parse_url

from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.endpoint_spec import EndpointSpec
from mindtrace.services.core.utils import generate_connection_manager


class TestGenerateConnectionManager:
    """Test suite for the generate_connection_manager function."""

    @pytest.fixture
    def mock_service_class(self):
        """Create a mock service class for testing."""
        mock_endpoint1 = Mock()
        mock_endpoint1.input_schema = Mock()
        mock_endpoint1.output_schema = Mock()

        mock_endpoint2 = Mock()
        mock_endpoint2.input_schema = None
        mock_endpoint2.output_schema = Mock()

        mock_service_class = Mock()
        mock_service_class.__name__ = "TestService"
        mock_service_class.__endpoints__ = {
            "test_endpoint": EndpointSpec(path="test_endpoint", method_name="test_endpoint", schema=mock_endpoint1),
            "no_input_endpoint": EndpointSpec(
                path="no_input_endpoint", method_name="no_input_endpoint", schema=mock_endpoint2
            ),
        }

        mock_service = Mock()
        mock_service._endpoints = {
            "test_endpoint": mock_endpoint1,
            "no_input_endpoint": mock_endpoint2,
        }
        mock_service_class.return_value = mock_service

        return mock_service_class, mock_service, mock_endpoint1, mock_endpoint2

    def test_generate_connection_manager_class_creation(self, mock_service_class):
        """Test that generate_connection_manager creates a proper class."""
        mock_service_class, mock_service, _, _ = mock_service_class

        ConnectionManagerClass = generate_connection_manager(mock_service_class)

        # Verify class name
        assert ConnectionManagerClass.__name__ == "TestServiceConnectionManager"

        # Verify it inherits from ConnectionManager
        assert issubclass(ConnectionManagerClass, ConnectionManager)

        # Verify service class was NOT instantiated (reads __endpoints__ directly)
        mock_service_class.assert_not_called()

    def test_generate_connection_manager_method_creation(self, mock_service_class):
        """Test that methods are created for each endpoint."""
        mock_service_class, mock_service, _, _ = mock_service_class

        ConnectionManagerClass = generate_connection_manager(mock_service_class)

        # Verify sync methods exist
        assert hasattr(ConnectionManagerClass, "test_endpoint")
        assert hasattr(ConnectionManagerClass, "no_input_endpoint")

        # Verify async methods exist
        assert hasattr(ConnectionManagerClass, "atest_endpoint")
        assert hasattr(ConnectionManagerClass, "ano_input_endpoint")

    def test_generate_connection_manager_method_documentation(self, mock_service_class):
        """Test that generated methods have proper documentation."""
        mock_service_class, mock_service, _, _ = mock_service_class

        ConnectionManagerClass = generate_connection_manager(mock_service_class)

        # Check sync method documentation
        test_method = getattr(ConnectionManagerClass, "test_endpoint")
        assert "Calls the `test_endpoint` pipeline at `/test_endpoint`" in test_method.__doc__

        # Check async method documentation
        atest_method = getattr(ConnectionManagerClass, "atest_endpoint")
        assert "Async version: Calls the `test_endpoint` pipeline at `/test_endpoint`" in atest_method.__doc__

    def test_generate_connection_manager_protected_methods_default(self, mock_service_class):
        """Test that default protected methods are not overridden."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Override __endpoints__ with protected + safe endpoints
        mock_service_class.__endpoints__ = {
            name: EndpointSpec(path=name, method_name=name, schema=mock_endpoint1)
            for name in ["shutdown", "ashutdown", "status", "astatus", "safe_endpoint"]
        }

        ConnectionManagerClass = generate_connection_manager(mock_service_class)

        # Protected methods should not be created as dynamic methods
        # (They may exist from the base class, but not as dynamic methods)
        assert hasattr(ConnectionManagerClass, "safe_endpoint")
        assert hasattr(ConnectionManagerClass, "asafe_endpoint")

    def test_generate_connection_manager_custom_protected_methods(self, mock_service_class):
        """Test custom protected methods parameter."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        mock_service_class.__endpoints__ = {
            name: EndpointSpec(path=name, method_name=name, schema=mock_endpoint1)
            for name in ["custom_protected", "safe_endpoint"]
        }

        ConnectionManagerClass = generate_connection_manager(mock_service_class, protected_methods=["custom_protected"])

        # Custom protected method should not be created
        # Safe endpoint should be created
        assert hasattr(ConnectionManagerClass, "safe_endpoint")
        assert hasattr(ConnectionManagerClass, "asafe_endpoint")

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_sync_call_success(self, mock_httpx, mock_service_class):
        """Test successful sync method call."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_httpx.post.return_value = mock_response

        # Setup input/output schemas
        mock_input_schema = Mock()
        mock_input_schema.return_value.model_dump.return_value = {"input": "data"}
        mock_output_schema = Mock()
        mock_output_schema.return_value = {"processed": "result"}

        mock_endpoint1.input_schema = mock_input_schema
        mock_endpoint1.output_schema = mock_output_schema

        ConnectionManagerClass = generate_connection_manager(mock_service_class)

        # Create instance and call method
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))
        _ = manager.test_endpoint(test_param="value")

        # Verify httpx call
        mock_httpx.post.assert_called_once_with("http://test.com/test_endpoint", json={"input": "data"}, timeout=60)

        # Verify input schema was called
        mock_input_schema.assert_called_once_with(test_param="value")

        # Verify output schema was called
        mock_output_schema.assert_called_once_with(result="success")

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_method_async_call_success(self, mock_httpx, mock_service_class):
        """Test successful async method call."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock async client and response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "async_success"}
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        # Setup schemas
        mock_input_schema = Mock()
        mock_input_schema.return_value.model_dump.return_value = {"async": "data"}
        mock_output_schema = Mock()
        mock_output_schema.return_value = {"async_processed": "result"}

        mock_endpoint1.input_schema = mock_input_schema
        mock_endpoint1.output_schema = mock_output_schema

        ConnectionManagerClass = generate_connection_manager(mock_service_class)

        # Create instance and call async method
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))
        _ = await manager.atest_endpoint(async_param="value")

        # Verify async client call
        mock_client.post.assert_called_once_with("http://test.com/test_endpoint", json={"async": "data"}, timeout=60)

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_http_error(self, mock_httpx, mock_service_class):
        """Test HTTP error handling in generated method."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_httpx.post.return_value = mock_response

        # Setup schemas
        mock_endpoint1.input_schema = None
        mock_endpoint1.output_schema = Mock()

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            manager.test_endpoint()

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_no_input_schema(self, mock_httpx, mock_service_class):
        """Test method generation with no input schema."""
        mock_service_class, mock_service, _, mock_endpoint2 = mock_service_class

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "no_input"}
        mock_httpx.post.return_value = mock_response

        # mock_endpoint2 has input_schema = None
        mock_endpoint2.output_schema = Mock()
        mock_endpoint2.output_schema.return_value = {"processed": "no_input"}

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        _ = manager.no_input_endpoint(raw_param="value")

        # Should pass kwargs directly as payload (but since input_schema is None, it creates empty payload)
        mock_httpx.post.assert_called_once_with("http://test.com/no_input_endpoint", json={}, timeout=60)

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_empty_response(self, mock_httpx, mock_service_class):
        """Test handling of empty response content."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock response with empty content
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = Exception("No JSON content")
        mock_httpx.post.return_value = mock_response

        mock_endpoint1.input_schema = None
        mock_endpoint1.output_schema = Mock()
        mock_endpoint1.output_schema.return_value = {"default": "response"}

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        _ = manager.test_endpoint()

        # Should call output schema with default success response
        mock_endpoint1.output_schema.assert_called_once_with(success=True)

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_validation_flags(self, mock_httpx, mock_service_class):
        """Test validate_input and validate_output flags."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"raw": "response"}
        mock_httpx.post.return_value = mock_response

        mock_endpoint1.input_schema = Mock()
        mock_endpoint1.output_schema = Mock()

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Test with validation disabled
        result = manager.test_endpoint(validate_input=False, validate_output=False, raw_param="value")

        # Should pass kwargs directly and return raw response
        mock_httpx.post.assert_called_once_with(
            "http://test.com/test_endpoint", json={"raw_param": "value"}, timeout=60
        )

        # Should not call schemas
        mock_endpoint1.input_schema.assert_not_called()
        mock_endpoint1.output_schema.assert_not_called()

        # Should return raw response
        assert result == {"raw": "response"}

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_no_input_schema_with_validate_input_false(self, mock_httpx, mock_service_class):
        """Test method generation with no input schema and validate_input=False."""
        mock_service_class, mock_service, _, mock_endpoint2 = mock_service_class

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "no_input_validate_false"}
        mock_httpx.post.return_value = mock_response

        # mock_endpoint2 has input_schema = None
        mock_endpoint2.output_schema = Mock()
        mock_endpoint2.output_schema.return_value = {"processed": "no_input"}

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Call with validate_input=False and kwargs
        _ = manager.no_input_endpoint(validate_input=False, raw_param="value")

        # Should pass kwargs directly as payload
        mock_httpx.post.assert_called_once_with(
            "http://test.com/no_input_endpoint", json={"raw_param": "value"}, timeout=60
        )

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_no_input_schema_with_validate_input_false(
        self, mock_httpx, mock_service_class
    ):
        """Test async method generation with no input schema and validate_input=False."""
        mock_service_class, mock_service, _, mock_endpoint2 = mock_service_class

        # Setup mock async client and response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "async_no_input_validate_false"}
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        # mock_endpoint2 has input_schema = None
        mock_endpoint2.output_schema = Mock()
        mock_endpoint2.output_schema.return_value = {"processed": "async_no_input"}

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Call async method with validate_input=False and kwargs
        _ = await manager.ano_input_endpoint(validate_input=False, async_param="value")

        # Should pass kwargs directly as payload
        mock_client.post.assert_called_once_with(
            "http://test.com/no_input_endpoint", json={"async_param": "value"}, timeout=60
        )

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_http_error(self, mock_httpx, mock_service_class):
        """Test async method HTTP error handling."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock async client with error response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_endpoint1.input_schema = None
        mock_endpoint1.output_schema = Mock()

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await manager.atest_endpoint()

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Bad Request"

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_empty_response(self, mock_httpx, mock_service_class):
        """Test async method handling of empty response."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock async client with empty response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = Exception("No JSON content")
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_endpoint1.input_schema = None
        mock_endpoint1.output_schema = Mock()
        mock_endpoint1.output_schema.return_value = {"default": "async_response"}

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        _ = await manager.atest_endpoint()

        # Should call output schema with default success response
        mock_endpoint1.output_schema.assert_called_once_with(success=True)

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_no_validate_output(self, mock_httpx, mock_service_class):
        """Test async method with validate_output=False returning raw result."""
        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class

        # Setup mock async client with normal response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"raw": "async_response_data"}
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_endpoint1.input_schema = None
        mock_endpoint1.output_schema = Mock()

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Call with validate_output=False
        result = await manager.atest_endpoint(validate_output=False)

        # Should return raw result without calling output schema
        assert result == {"raw": "async_response_data"}
        mock_endpoint1.output_schema.assert_not_called()

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_multiple_args_error(self, mock_httpx, mock_service_class):
        """Test that method raises error when called with multiple args."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise ValueError when called with multiple args
        with pytest.raises(ValueError, match="must be called with either kwargs or a single argument"):
            manager.test_endpoint(TestInput(value="test"), "extra_arg")

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_wrong_arg_type_error(self, mock_httpx, mock_service_class):
        """Test that method raises error when arg is wrong type."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise ValueError when called with wrong type
        with pytest.raises(ValueError, match="must be called with either kwargs or a single argument"):
            manager.test_endpoint("not_a_test_input")

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_args_and_kwargs_error(self, mock_httpx, mock_service_class):
        """Test that method raises error when called with both args and kwargs."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise ValueError when called with both args and kwargs
        with pytest.raises(ValueError, match="must be called with either kwargs or a single argument"):
            manager.test_endpoint(TestInput(value="test"), extra_param="value")

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_multiple_args_error(self, mock_httpx, mock_service_class):
        """Test that async method raises error when called with multiple args."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise ValueError when called with multiple args
        with pytest.raises(ValueError, match="must be called with either kwargs or a single argument"):
            await manager.atest_endpoint(TestInput(value="test"), "extra_arg")

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_wrong_arg_type_error(self, mock_httpx, mock_service_class):
        """Test that async method raises error when arg is wrong type."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise ValueError when called with wrong type
        with pytest.raises(ValueError, match="must be called with either kwargs or a single argument"):
            await manager.atest_endpoint("not_a_test_input")

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_args_and_kwargs_error(self, mock_httpx, mock_service_class):
        """Test that async method raises error when called with both args and kwargs."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should raise ValueError when called with both args and kwargs
        with pytest.raises(ValueError, match="must be called with either kwargs or a single argument"):
            await manager.atest_endpoint(TestInput(value="test"), extra_param="value")

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_single_valid_arg(self, mock_httpx, mock_service_class):
        """Test that method works with a single valid arg."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_httpx.post.return_value = mock_response

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Call with single valid arg
        result = manager.test_endpoint(TestInput(value="test"))

        # Should call httpx with dumped payload
        mock_httpx.post.assert_called_once_with("http://test.com/test_endpoint", json={"value": "test"}, timeout=60)
        assert result == {"result": "success"}

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_single_valid_arg(self, mock_httpx, mock_service_class):
        """Test that async method works with a single valid arg."""
        from pydantic import BaseModel

        class TestInput(BaseModel):
            value: str

        mock_service_class, mock_service, mock_endpoint1, _ = mock_service_class
        mock_endpoint1.input_schema = TestInput
        mock_endpoint1.output_schema = None

        # Setup mock async client and response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "async_success"}
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        ConnectionManagerClass = generate_connection_manager(mock_service_class)
        manager = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Call async method with single valid arg
        result = await manager.atest_endpoint(TestInput(value="test"))

        # Should call async client with dumped payload
        mock_client.post.assert_called_once_with("http://test.com/test_endpoint", json={"value": "test"}, timeout=60)
        assert result == {"result": "async_success"}


class TestUtilsIntegration:
    """Integration tests for utils functions working together."""

    def test_full_workflow_mock(self):
        """Test a complete workflow using all utils functions with mocks."""

        # Create mock connection manager
        class MockConnectionManager:
            def __init__(self, url):
                self.url = url

        # Create mock service class with explicit registration
        class MockService:
            def __init__(self):
                self._endpoints = {}

        MockService._client_interface = MockConnectionManager

        # Verify registration worked
        assert MockService._client_interface == MockConnectionManager

        # Test that we can generate a connection manager using mock
        mock_service_cls = Mock()
        mock_service_cls.__name__ = "MockService"
        mock_service_cls.__endpoints__ = {}

        GeneratedConnectionManager = generate_connection_manager(mock_service_cls)

        assert GeneratedConnectionManager.__name__ == "MockServiceConnectionManager"
        assert issubclass(GeneratedConnectionManager, ConnectionManager)
