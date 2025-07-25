from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.gateway.proxy_connection_manager import ProxyConnectionManager


class DummyInput:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self):
        return self.__dict__


class DummyOutput:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class DummySchema:
    input_schema = DummyInput
    output_schema = DummyOutput
    name = "dummy"


class DummyCM(ConnectionManager):
    pass

class DummyCMWithServiceEndpoints(ConnectionManager):
    def __init__(self, **kwargs):
        self._service_endpoints: dict[str, type] = {"test": DummySchema}

def test_initialization():
    """Test that ProxyConnectionManager initializes correctly."""
    dummy_cm = DummyCMWithServiceEndpoints()
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    # Use object.__getattribute__ to avoid triggering the custom __getattribute__
    assert object.__getattribute__(proxy_cm, "gateway_url") == "http://gateway"
    assert object.__getattribute__(proxy_cm, "app_name") == "app"
    assert object.__getattribute__(proxy_cm, "original_cm") == dummy_cm


def test_url_normalization():
    """Test that gateway URL is properly normalized (no trailing slash)."""
    dummy_cm = DummyCMWithServiceEndpoints()
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway/", app_name="app", original_cm=dummy_cm
    )
    
    assert object.__getattribute__(proxy_cm, "gateway_url") == "http://gateway"


def test_service_endpoints_extraction():
    """Test that service endpoints are properly extracted from the connection manager."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")
    assert "dummy" in service_endpoints
    assert service_endpoints["dummy"] == DummySchema


@patch("requests.post")
def test_sync_proxy_method_success(mock_post):
    """Test successful sync proxy method call."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}
    mock_post.return_value = mock_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the dynamically created method directly from instance dict
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    dummy_method = instance_dict["dummy"]

    result = dummy_method(foo="bar")

    # Result is wrapped in DummyOutput because schema validation is applied
    assert isinstance(result, DummyOutput)
    assert result.result == "ok"
    mock_post.assert_called_once_with("http://gateway/app/dummy", json={"foo": "bar"}, timeout=60)


@patch("requests.post")
def test_sync_proxy_method_http_error(mock_post):
    """Test sync proxy method with HTTP error."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    dummy_method = instance_dict["dummy"]

    with pytest.raises(RuntimeError, match="Gateway proxy request failed: Internal Server Error"):
        dummy_method(foo="bar")


@patch("requests.post")
def test_sync_proxy_method_json_error(mock_post):
    """Test sync proxy method with JSON parsing error."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("bad json")
    mock_post.return_value = mock_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    dummy_method = instance_dict["dummy"]

    result = dummy_method(foo="bar")
    # When JSON parsing fails, it falls back to {"success": True} and then applies output validation
    assert isinstance(result, DummyOutput)
    assert result.success is True


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_success(mock_client_class):
    """Test successful async proxy method call."""
    mock_client = AsyncMock()
    mock_response = Mock()  # Use regular Mock, not AsyncMock
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}  # json() is synchronous in httpx
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    adummy_method = instance_dict["adummy"]

    result = await adummy_method(foo="bar")

    # Result is wrapped in DummyOutput because schema validation is applied
    assert isinstance(result, DummyOutput)
    assert result.result == "ok"
    mock_client.post.assert_awaited_once_with("http://gateway/app/dummy", json={"foo": "bar"})


def test_getattribute_internal_attrs():
    """Test that internal attributes are accessed directly."""
    dummy_cm = DummyCMWithServiceEndpoints()
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    # These should be accessible via the normal __getattribute__ without HTTP calls
    assert proxy_cm.gateway_url == "http://gateway"
    assert proxy_cm.app_name == "app"
    assert proxy_cm.original_cm == dummy_cm


@patch("requests.get")
def test_getattribute_proxy_property_get_success(mock_get):
    """Test property access via GET request."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"foo": "bar"}
    mock_get.return_value = mock_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    result = proxy_cm.some_property
    assert result["foo"] == "bar"
    mock_get.assert_called_once_with("http://gateway/app/some_property", timeout=60)


def test_dynamic_method_creation():
    """Test that sync and async methods are created for each endpoint."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    instance_dict = object.__getattribute__(proxy_cm, "__dict__")

    # Both sync and async methods should be created
    assert "test_endpoint" in instance_dict
    assert "atest_endpoint" in instance_dict
    assert callable(instance_dict["test_endpoint"])
    assert callable(instance_dict["atest_endpoint"])


def test_extract_service_endpoints_from_class_attribute():
    """Test that _extract_service_endpoints correctly uses original_cm.__class__._service_endpoints (line 50)."""

    # Create a mock connection manager class with _service_endpoints set on the class
    class MockConnectionManagerClass:
        # This simulates what generate_connection_manager does
        _service_endpoints = {"test_endpoint": DummySchema, "another_endpoint": DummySchema}

    mock_cm = MockConnectionManagerClass()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=mock_cm)

    # Verify that the endpoints were extracted from the class attribute
    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")

    # Should have extracted endpoints from original_cm.__class__._service_endpoints
    assert "test_endpoint" in service_endpoints
    assert "another_endpoint" in service_endpoints
    assert service_endpoints["test_endpoint"] == DummySchema
    assert service_endpoints["another_endpoint"] == DummySchema

    # Verify that proxy methods were created for these endpoints
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    assert "test_endpoint" in instance_dict
    assert "atest_endpoint" in instance_dict
    assert "another_endpoint" in instance_dict
    assert "aanother_endpoint" in instance_dict


def test_extract_service_endpoints_from_instance_service_class():
    """Test that _extract_service_endpoints correctly uses original_cm._service_class (lines 51-55)."""

    # Create a mock service class that has endpoints
    class MockService:
        def __init__(self):
            self._endpoints = {"instance_endpoint": DummySchema, "service_endpoint": DummySchema}

    # Create a mock connection manager instance with _service_class set on the instance
    class MockConnectionManager(ConnectionManager):
        def __init__(self, **kwargs):
            self._service_class = MockService
    
    mock_cm = MockConnectionManager()
    # This simulates a case where the instance stores the service class reference
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=mock_cm
    )
    
    # Verify that the endpoints were extracted from the service class via instance attribute
    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")

    # Should have extracted endpoints from temp_service._endpoints where temp_service = original_cm._service_class()
    assert "instance_endpoint" in service_endpoints
    assert "service_endpoint" in service_endpoints
    assert service_endpoints["instance_endpoint"] == DummySchema
    assert service_endpoints["service_endpoint"] == DummySchema

    # Verify that proxy methods were created for these endpoints
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    assert "instance_endpoint" in instance_dict
    assert "ainstance_endpoint" in instance_dict
    assert "service_endpoint" in instance_dict
    assert "aservice_endpoint" in instance_dict


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_input_validation_fallback(mock_client_class):
    """Test async proxy method fallback when input validation fails (lines 107-109)."""

    # Create a schema with an input_schema that will fail validation
    class FailingInputSchema:
        def __init__(self, **kwargs):
            # Always raise an exception to trigger the fallback
            raise ValueError("Input validation failed")

        def model_dump(self):
            return {}

    class SchemaWithFailingInput:
        input_schema = FailingInputSchema
        output_schema = DummyOutput
        name = "failing_input"

    # Set up mocks for HTTP request
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with failing input schema
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_input": SchemaWithFailingInput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    afailing_input_method = instance_dict["afailing_input"]

    # Call the async method with some kwargs
    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = await afailing_input_method(**test_kwargs)

    # Verify that the HTTP request was made with raw kwargs (fallback behavior)
    mock_client.post.assert_awaited_once_with(
        "http://gateway/app/failing_input",
        json=test_kwargs,  # Should be raw kwargs, not validated input
    )

    # Verify that the result was processed correctly
    assert isinstance(result, DummyOutput)
    assert result.result == "success"


@patch("requests.post")
def test_sync_proxy_method_input_validation_fallback(mock_post):
    """Test sync proxy method fallback when input validation fails (equivalent to lines 107-109 but in sync version)."""

    # Create a schema with an input_schema that will fail validation
    class FailingInputSchema:
        def __init__(self, **kwargs):
            # Always raise an exception to trigger the fallback
            raise ValueError("Input validation failed")

        def model_dump(self):
            return {}

    class SchemaWithFailingInput:
        input_schema = FailingInputSchema
        output_schema = DummyOutput
        name = "failing_input"

    # Set up mocks for HTTP request
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_post.return_value = mock_response

    # Create connection manager with failing input schema
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_input": SchemaWithFailingInput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the sync method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    failing_input_method = instance_dict["failing_input"]

    # Call the sync method with some kwargs
    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = failing_input_method(**test_kwargs)

    # Verify that the HTTP request was made with raw kwargs (fallback behavior)
    mock_post.assert_called_once_with(
        "http://gateway/app/failing_input",
        json=test_kwargs,  # Should be raw kwargs, not validated input
        timeout=60,
    )

    # Verify that the result was processed correctly
    assert isinstance(result, DummyOutput)
    assert result.result == "success"


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_no_input_schema(mock_client_class):
    """Test async proxy method when no input_schema is available (line 111)."""

    # Create a schema with NO input_schema (None)
    class SchemaWithoutInputSchema:
        input_schema = None  # This will trigger the else clause at line 111
        output_schema = DummyOutput
        name = "no_input_schema"

    # Set up mocks for HTTP request
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "no_validation"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with schema that has no input validation
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"no_input_schema": SchemaWithoutInputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    ano_input_schema_method = instance_dict["ano_input_schema"]

    # Call the async method with some kwargs
    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = await ano_input_schema_method(**test_kwargs)

    # Verify that the HTTP request was made with raw kwargs (no validation)
    mock_client.post.assert_awaited_once_with(
        "http://gateway/app/no_input_schema",
        json=test_kwargs,  # Should be raw kwargs since no input_schema
    )

    # Verify that the result was processed correctly
    assert isinstance(result, DummyOutput)
    assert result.result == "no_validation"


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_missing_input_schema_attribute(mock_client_class):
    """Test async proxy method when input_schema attribute is missing entirely (line 111)."""

    # Create a schema that doesn't have input_schema attribute at all
    class SchemaWithMissingInputSchema:
        # No input_schema attribute at all
        output_schema = DummyOutput
        name = "missing_input_schema"

    # Set up mocks for HTTP request
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "no_input_attr"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with schema that has no input_schema attribute
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"missing_input_schema": SchemaWithMissingInputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    amissing_input_schema_method = instance_dict["amissing_input_schema"]

    # Call the async method with some kwargs
    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = await amissing_input_schema_method(**test_kwargs)

    # Verify that the HTTP request was made with raw kwargs (no validation)
    mock_client.post.assert_awaited_once_with(
        "http://gateway/app/missing_input_schema",
        json=test_kwargs,  # Should be raw kwargs since no input_schema attribute
    )

    # Verify that the result was processed correctly
    assert isinstance(result, DummyOutput)
    assert result.result == "no_input_attr"


def test_infer_endpoints_from_methods():
    """Test fallback endpoint inference when service endpoints are not available."""
    class MockCM(ConnectionManager):
        def some_method(self):
            pass

        def another_method(self):
            pass

        def shutdown(self):  # This should be filtered out
            pass

    mock_cm = MockCM()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=mock_cm)

    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")

    # Should have inferred endpoints for public methods, excluding protected ones
    assert "some_method" in service_endpoints
    assert "another_method" in service_endpoints
    assert "shutdown" not in service_endpoints  # Should be filtered out


def test_extract_service_endpoints_from_class_service_class():
    """Test that _extract_service_endpoints correctly uses original_cm.__class__._service_class (lines 45-47)."""

    # Create a mock service class that has endpoints
    class MockService:
        def __init__(self):
            self._endpoints = {"class_service_endpoint": DummySchema, "another_class_endpoint": DummySchema}

    # Create a mock connection manager class with _service_class set on the class
    class MockConnectionManagerClass(ConnectionManager):
        _service_class = MockService  # This simulates the first branch in _extract_service_endpoints

    mock_cm = MockConnectionManagerClass()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=mock_cm)

    # Verify that the endpoints were extracted from the service class via class attribute
    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")

    # Should have extracted endpoints from temp_service._endpoints where temp_service = original_cm.__class__._service_class()
    assert "class_service_endpoint" in service_endpoints
    assert "another_class_endpoint" in service_endpoints
    assert service_endpoints["class_service_endpoint"] == DummySchema
    assert service_endpoints["another_class_endpoint"] == DummySchema

    # Verify that proxy methods were created for these endpoints
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    assert "class_service_endpoint" in instance_dict
    assert "aclass_service_endpoint" in instance_dict
    assert "another_class_endpoint" in instance_dict
    assert "aanother_class_endpoint" in instance_dict


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_http_error(mock_client_class):
    """Test async proxy method when HTTP request returns non-200 status (line 118)."""
    # Set up mocks for HTTP request with error status
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with schema
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"error_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    aerror_endpoint_method = instance_dict["aerror_endpoint"]

    # Call the async method - should raise RuntimeError
    with pytest.raises(RuntimeError, match="Gateway proxy request failed: Internal Server Error"):
        await aerror_endpoint_method(param="value")


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_json_parsing_error(mock_client_class):
    """Test async proxy method when JSON parsing fails (lines 123-124)."""
    # Set up mocks for HTTP request with unparseable JSON
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("Invalid JSON")
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with schema that has no output validation
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"json_error_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    ajson_error_endpoint_method = instance_dict["ajson_error_endpoint"]

    # Call the async method - should fallback to {"success": True}
    result = await ajson_error_endpoint_method(param="value")

    # Should get the fallback result wrapped in output schema
    assert isinstance(result, DummyOutput)
    assert result.success is True


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_output_validation_error(mock_client_class):
    """Test async proxy method when output validation fails (lines 130-134)."""

    # Create a schema with an output_schema that will fail validation
    class FailingOutputSchema:
        def __init__(self, **kwargs):
            # Always raise an exception to trigger the fallback
            raise ValueError("Output validation failed")

    class SchemaWithFailingOutput:
        input_schema = None
        output_schema = FailingOutputSchema
        name = "failing_output"

    # Set up mocks for HTTP request
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with failing output schema
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_output": SchemaWithFailingOutput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    afailing_output_method = instance_dict["afailing_output"]

    # Call the async method - should fallback to raw result when output validation fails
    result = await afailing_output_method(param="value")

    # Should get the raw result (not wrapped in output schema due to validation failure)
    assert result == {"result": "success"}


@patch("requests.post")
def test_sync_proxy_method_json_parsing_error(mock_post):
    """Test sync proxy method when JSON parsing fails (lines 168-170)."""
    # Set up mocks for HTTP request with unparseable JSON
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("Invalid JSON")
    mock_post.return_value = mock_response

    # Create connection manager with schema that has no output validation
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"json_error_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the sync method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    json_error_endpoint_method = instance_dict["json_error_endpoint"]

    # Call the sync method - should fallback to {"success": True}
    result = json_error_endpoint_method(param="value")

    # Should get the fallback result wrapped in output schema
    assert isinstance(result, DummyOutput)
    assert result.success is True


@patch("requests.get")
def test_getattribute_get_request_json_error(mock_get):
    """Test __getattribute__ when GET request succeeds but JSON parsing fails (lines 209-220)."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("JSON parse error")
    mock_response.text = "raw response text"
    mock_get.return_value = mock_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Access a non-internal attribute to trigger the gateway request path
    result = proxy_cm.some_property

    # Should return the raw text when JSON parsing fails
    assert result == "raw response text"
    mock_get.assert_called_once_with("http://gateway/app/some_property", timeout=60)


@patch("requests.get")
@patch("requests.post")
def test_getattribute_get_fails_post_succeeds_json_error(mock_post, mock_get):
    """Test __getattribute__ when GET fails, POST succeeds but JSON parsing fails (lines 209-220)."""
    # GET request fails
    mock_get_response = Mock()
    mock_get_response.status_code = 404
    mock_get.return_value = mock_get_response

    # POST request succeeds but JSON parsing fails
    mock_post_response = Mock()
    mock_post_response.status_code = 200
    mock_post_response.json.side_effect = Exception("JSON parse error")
    mock_post_response.text = "post response text"
    mock_post.return_value = mock_post_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Access a non-internal attribute to trigger the gateway request path
    result = proxy_cm.some_property

    # Should return the raw text from POST when JSON parsing fails
    assert result == "post response text"
    mock_get.assert_called_once_with("http://gateway/app/some_property", timeout=60)
    mock_post.assert_called_once_with("http://gateway/app/some_property", timeout=60)


def test_getattr_fallback():
    """Test __getattr__ fallback method."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # This should trigger __getattr__ since __getattribute__ doesn't handle this case
    # We need to bypass __getattribute__ to test __getattr__
    with pytest.raises(AttributeError, match="'ProxyConnectionManager' object has no attribute 'nonexistent_attr'"):
        object.__getattribute__(proxy_cm, "__class__").__getattr__(proxy_cm, "nonexistent_attr")


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_output_schema_no_validation(mock_client_class):
    """Test async proxy method when output_schema is None (line 134)."""

    # Create a schema with NO output_schema (None)
    class SchemaWithoutOutputSchema:
        input_schema = None
        output_schema = None  # This will trigger the else clause at line 134
        name = "no_output_schema"

    # Set up mocks for HTTP request
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "raw_result"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    # Create connection manager with schema that has no output validation
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"no_output_schema": SchemaWithoutOutputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the async method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    ano_output_schema_method = instance_dict["ano_output_schema"]

    # Call the async method
    result = await ano_output_schema_method(param="value")

    # Should get the raw result (no output validation)
    assert result == {"result": "raw_result"}


@patch("requests.post")
def test_sync_proxy_method_output_schema_no_validation(mock_post):
    """Test sync proxy method when output_schema is None (line 171)."""

    # Create a schema with NO output_schema (None)
    class SchemaWithoutOutputSchema:
        input_schema = None
        output_schema = None  # This will trigger the else clause
        name = "no_output_schema"

    # Set up mocks for HTTP request
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "raw_result"}
    mock_post.return_value = mock_response

    # Create connection manager with schema that has no output validation
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"no_output_schema": SchemaWithoutOutputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the sync method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    no_output_schema_method = instance_dict["no_output_schema"]

    # Call the sync method
    result = no_output_schema_method(param="value")

    # Should get the raw result (no output validation)
    assert result == {"result": "raw_result"}


@patch("requests.post")
def test_sync_proxy_method_output_validation_error(mock_post):
    """Test sync proxy method when output validation fails (lines 168-172)."""

    # Create a schema with an output_schema that will fail validation
    class FailingOutputSchema:
        def __init__(self, **kwargs):
            # Always raise an exception to trigger the fallback
            raise ValueError("Output validation failed")

    class SchemaWithFailingOutput:
        input_schema = None
        output_schema = FailingOutputSchema
        name = "failing_output"

    # Set up mocks for HTTP request
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_post.return_value = mock_response

    # Create connection manager with failing output schema
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_output": SchemaWithFailingOutput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Get the sync method
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    failing_output_method = instance_dict["failing_output"]

    # Call the sync method - should fallback to raw result when output validation fails
    result = failing_output_method(param="value")

    # Should get the raw result (not wrapped in output schema due to validation failure)
    assert result == {"result": "success"}


@patch("requests.get")
@patch("requests.post")
def test_getattribute_both_get_and_post_fail(mock_post, mock_get):
    """Test __getattribute__ when both GET and POST requests fail (line 220)."""
    # Mock both GET and POST to return non-200 status codes
    mock_get_response = Mock()
    mock_get_response.status_code = 404
    mock_get.return_value = mock_get_response

    mock_post_response = Mock()
    mock_post_response.status_code = 500
    mock_post_response.text = "Internal Server Error"
    mock_post.return_value = mock_post_response
    
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Use object.__getattribute__ to call the ProxyConnectionManager's __getattribute__ method directly
    # This will trigger the gateway request path, and both GET and POST will fail
    with pytest.raises(AttributeError, match="Gateway request failed for 'some_property': 500 - Internal Server Error"):
        ProxyConnectionManager.__getattribute__(proxy_cm, "some_property")

    # Verify both GET and POST were called
    mock_get.assert_called_once_with("http://gateway/app/some_property", timeout=60)
    mock_post.assert_called_once_with("http://gateway/app/some_property", timeout=60)


def test_getattribute_line_195_proxy_method_access():
    """Test that line 195 is executed when accessing proxy methods from instance dict."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test_method": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    # Verify the proxy method was created and is in instance dict
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    assert "test_method" in instance_dict
    assert "atest_method" in instance_dict

    # Access the proxy method - this should hit line 195
    sync_method = proxy_cm.test_method
    async_method = proxy_cm.atest_method

    # Verify we got the actual methods
    assert callable(sync_method)
    assert callable(async_method)
    assert sync_method.__name__ == "test_method"
    assert async_method.__name__ == "atest_method"
