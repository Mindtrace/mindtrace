from unittest.mock import Mock, patch, AsyncMock

import httpx
import pytest
import requests

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

class DummyCM:
    pass

def test_initialization():
    """Test that ProxyConnectionManager initializes correctly."""
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"test": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    # Use object.__getattribute__ to avoid triggering the custom __getattribute__
    assert object.__getattribute__(proxy_cm, "gateway_url") == "http://gateway"
    assert object.__getattribute__(proxy_cm, "app_name") == "app"
    assert object.__getattribute__(proxy_cm, "original_cm") == dummy_cm

def test_url_normalization():
    """Test that gateway URL is properly normalized (no trailing slash)."""
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"test": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway/", app_name="app", original_cm=dummy_cm
    )
    
    assert object.__getattribute__(proxy_cm, "gateway_url") == "http://gateway"

def test_service_endpoints_extraction():
    """Test that service endpoints are properly extracted from the connection manager."""
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")
    assert "dummy" in service_endpoints
    assert service_endpoints["dummy"] == DummySchema

@patch('requests.post')
def test_sync_proxy_method_success(mock_post):
    """Test successful sync proxy method call."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}
    mock_post.return_value = mock_response
    
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    # Get the dynamically created method directly from instance dict
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    dummy_method = instance_dict["dummy"]
    
    result = dummy_method(foo="bar")
    
    # Result is wrapped in DummyOutput because schema validation is applied
    assert isinstance(result, DummyOutput)
    assert result.result == "ok"
    mock_post.assert_called_once_with(
        "http://gateway/app/dummy",
        json={"foo": "bar"},
        timeout=60
    )

@patch('requests.post')
def test_sync_proxy_method_http_error(mock_post):
    """Test sync proxy method with HTTP error."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response
    
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    dummy_method = instance_dict["dummy"]
    
    with pytest.raises(RuntimeError, match="Gateway proxy request failed: Internal Server Error"):
        dummy_method(foo="bar")

@patch('requests.post')
def test_sync_proxy_method_json_error(mock_post):
    """Test sync proxy method with JSON parsing error."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("bad json")
    mock_post.return_value = mock_response
    
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    dummy_method = instance_dict["dummy"]
    
    result = dummy_method(foo="bar")
    # When JSON parsing fails, it falls back to {"success": True} and then applies output validation
    assert isinstance(result, DummyOutput)
    assert result.success == True

@patch('httpx.AsyncClient')
@pytest.mark.asyncio
async def test_async_proxy_method_success(mock_client_class):
    """Test successful async proxy method call."""
    mock_client = AsyncMock()
    mock_response = Mock()  # Use regular Mock, not AsyncMock
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}  # json() is synchronous in httpx
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    adummy_method = instance_dict["adummy"]
    
    result = await adummy_method(foo="bar")
    
    # Result is wrapped in DummyOutput because schema validation is applied
    assert isinstance(result, DummyOutput)
    assert result.result == "ok"
    mock_client.post.assert_awaited_once_with(
        "http://gateway/app/dummy",
        json={"foo": "bar"}
    )

def test_getattribute_internal_attrs():
    """Test that internal attributes are accessed directly."""
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    # These should be accessible via the normal __getattribute__ without HTTP calls
    assert proxy_cm.gateway_url == "http://gateway"
    assert proxy_cm.app_name == "app"
    assert proxy_cm.original_cm == dummy_cm

@patch('requests.get')
def test_getattribute_proxy_property_get_success(mock_get):
    """Test property access via GET request."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"foo": "bar"}
    mock_get.return_value = mock_response
    
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"dummy": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    result = proxy_cm.some_property
    assert result["foo"] == "bar"
    mock_get.assert_called_once_with("http://gateway/app/some_property", timeout=60)

def test_dynamic_method_creation():
    """Test that sync and async methods are created for each endpoint."""
    dummy_cm = DummyCM()
    dummy_cm._service_endpoints = {"test_endpoint": DummySchema}
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=dummy_cm
    )
    
    instance_dict = object.__getattribute__(proxy_cm, "__dict__")
    
    # Both sync and async methods should be created
    assert "test_endpoint" in instance_dict
    assert "atest_endpoint" in instance_dict
    assert callable(instance_dict["test_endpoint"])
    assert callable(instance_dict["atest_endpoint"])

def test_infer_endpoints_from_methods():
    """Test fallback endpoint inference when service endpoints are not available."""
    class MockCM:
        def some_method(self):
            pass
        
        def another_method(self):
            pass
        
        def shutdown(self):  # This should be filtered out
            pass
    
    mock_cm = MockCM()
    
    proxy_cm = ProxyConnectionManager(
        gateway_url="http://gateway", app_name="app", original_cm=mock_cm
    )
    
    service_endpoints = object.__getattribute__(proxy_cm, "_service_endpoints")
    
    # Should have inferred endpoints for public methods, excluding protected ones
    assert "some_method" in service_endpoints
    assert "another_method" in service_endpoints
    assert "shutdown" not in service_endpoints  # Should be filtered out
