from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.endpoint_spec import EndpointSpec
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

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    assert proxy_cm.gateway_url == "http://gateway"
    assert proxy_cm.app_name == "app"
    assert proxy_cm.original_cm == dummy_cm


def test_url_normalization():
    """Test that gateway URL is properly normalized (no trailing slash)."""
    dummy_cm = DummyCMWithServiceEndpoints()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway/", app_name="app", original_cm=dummy_cm)

    assert proxy_cm.gateway_url == "http://gateway"


def test_service_endpoints_extraction():
    """Test that service endpoints are properly extracted from the connection manager."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    assert "dummy" in proxy_cm._service_endpoints
    assert proxy_cm._service_endpoints["dummy"] == DummySchema


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_success(mock_httpx):
    """Test successful sync proxy method call."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    dummy_method = proxy_cm.__dict__["dummy"]
    result = dummy_method(foo="bar")

    assert isinstance(result, DummyOutput)
    assert result.result == "ok"
    mock_httpx.post.assert_called_once_with("http://gateway/app/dummy", json={"foo": "bar"}, timeout=60)


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_http_error(mock_httpx):
    """Test sync proxy method with HTTP error."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    dummy_method = proxy_cm.__dict__["dummy"]

    with pytest.raises(HTTPException) as exc_info:
        dummy_method(foo="bar")
    assert exc_info.value.status_code == 500


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_json_error(mock_httpx):
    """Test sync proxy method with JSON parsing error."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("bad json")
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    dummy_method = proxy_cm.__dict__["dummy"]
    result = dummy_method(foo="bar")
    assert isinstance(result, DummyOutput)
    assert result.success is True


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_success(mock_client_class):
    """Test successful async proxy method call."""
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"dummy": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    adummy_method = proxy_cm.__dict__["adummy"]
    result = await adummy_method(foo="bar")

    assert isinstance(result, DummyOutput)
    assert result.result == "ok"
    mock_client.post.assert_awaited_once_with("http://gateway/app/dummy", json={"foo": "bar"})


def test_internal_attrs_accessible():
    """Test that internal attributes are accessible normally."""
    dummy_cm = DummyCMWithServiceEndpoints()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    assert proxy_cm.gateway_url == "http://gateway"
    assert proxy_cm.app_name == "app"
    assert proxy_cm.original_cm == dummy_cm


def test_dynamic_method_creation():
    """Test that sync and async methods are created for each endpoint."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    assert "test_endpoint" in proxy_cm.__dict__
    assert "atest_endpoint" in proxy_cm.__dict__
    assert callable(proxy_cm.__dict__["test_endpoint"])
    assert callable(proxy_cm.__dict__["atest_endpoint"])


def test_extract_service_endpoints_from_class_attribute():
    """Test that _extract_service_endpoints correctly uses original_cm.__class__._service_endpoints."""

    class MockConnectionManagerClass:
        _service_endpoints = {"test_endpoint": DummySchema, "another_endpoint": DummySchema}

    mock_cm = MockConnectionManagerClass()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=mock_cm)

    assert "test_endpoint" in proxy_cm._service_endpoints
    assert "another_endpoint" in proxy_cm._service_endpoints
    assert "test_endpoint" in proxy_cm.__dict__
    assert "atest_endpoint" in proxy_cm.__dict__


def test_extract_service_endpoints_from_service_class():
    """Test that _extract_service_endpoints correctly uses original_cm.__class__._service_class."""

    class MockService:
        __endpoints__ = {
            "endpoint_a": EndpointSpec(path="endpoint_a", method_name="endpoint_a", schema=DummySchema),
            "endpoint_b": EndpointSpec(path="endpoint_b", method_name="endpoint_b", schema=DummySchema),
        }

    class MockConnectionManagerClass:
        _service_class = MockService

    mock_cm = MockConnectionManagerClass()

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=mock_cm)

    assert "endpoint_a" in proxy_cm._service_endpoints
    assert "endpoint_b" in proxy_cm._service_endpoints
    assert proxy_cm._service_endpoints["endpoint_a"] == DummySchema


def test_extract_service_endpoints_raises_on_unknown_cm():
    """Test that _extract_service_endpoints raises ValueError for unknown CM types."""

    class PlainCM:
        pass

    with pytest.raises(ValueError, match="Cannot extract endpoints"):
        ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=PlainCM())


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_input_validation_fallback(mock_client_class):
    """Test async proxy method fallback when input validation fails."""

    class FailingInputSchema:
        def __init__(self, **kwargs):
            raise ValueError("Input validation failed")

        def model_dump(self):
            return {}

    class SchemaWithFailingInput:
        input_schema = FailingInputSchema
        output_schema = DummyOutput
        name = "failing_input"

    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_input": SchemaWithFailingInput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    afailing_input_method = proxy_cm.__dict__["afailing_input"]

    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = await afailing_input_method(**test_kwargs)

    mock_client.post.assert_awaited_once_with("http://gateway/app/failing_input", json=test_kwargs)
    assert isinstance(result, DummyOutput)
    assert result.result == "success"


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_input_validation_fallback(mock_httpx):
    """Test sync proxy method fallback when input validation fails."""

    class FailingInputSchema:
        def __init__(self, **kwargs):
            raise ValueError("Input validation failed")

        def model_dump(self):
            return {}

    class SchemaWithFailingInput:
        input_schema = FailingInputSchema
        output_schema = DummyOutput
        name = "failing_input"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_input": SchemaWithFailingInput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    failing_input_method = proxy_cm.__dict__["failing_input"]

    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = failing_input_method(**test_kwargs)

    mock_httpx.post.assert_called_once_with("http://gateway/app/failing_input", json=test_kwargs, timeout=60)
    assert isinstance(result, DummyOutput)
    assert result.result == "success"


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_no_input_schema(mock_client_class):
    """Test async proxy method when no input_schema is available."""

    class SchemaWithoutInputSchema:
        input_schema = None
        output_schema = DummyOutput
        name = "no_input_schema"

    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "no_validation"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"no_input_schema": SchemaWithoutInputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    ano_input_schema_method = proxy_cm.__dict__["ano_input_schema"]

    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = await ano_input_schema_method(**test_kwargs)

    mock_client.post.assert_awaited_once_with("http://gateway/app/no_input_schema", json=test_kwargs)
    assert isinstance(result, DummyOutput)
    assert result.result == "no_validation"


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_missing_input_schema_attribute(mock_client_class):
    """Test async proxy method when input_schema attribute is missing entirely."""

    class SchemaWithMissingInputSchema:
        output_schema = DummyOutput
        name = "missing_input_schema"

    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "no_input_attr"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"missing_input_schema": SchemaWithMissingInputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    amissing_method = proxy_cm.__dict__["amissing_input_schema"]

    test_kwargs = {"param1": "value1", "param2": "value2"}
    result = await amissing_method(**test_kwargs)

    mock_client.post.assert_awaited_once_with("http://gateway/app/missing_input_schema", json=test_kwargs)
    assert isinstance(result, DummyOutput)
    assert result.result == "no_input_attr"


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_http_error(mock_client_class):
    """Test async proxy method when HTTP request returns non-200 status."""
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"error_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    aerror_method = proxy_cm.__dict__["aerror_endpoint"]

    with pytest.raises(HTTPException) as exc_info:
        await aerror_method(param="value")
    assert exc_info.value.status_code == 500


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_json_parsing_error(mock_client_class):
    """Test async proxy method when JSON parsing fails."""
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("Invalid JSON")
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"json_error_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    ajson_error_method = proxy_cm.__dict__["ajson_error_endpoint"]

    result = await ajson_error_method(param="value")
    assert isinstance(result, DummyOutput)
    assert result.success is True


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_output_validation_error(mock_client_class):
    """Test async proxy method when output validation fails."""

    class FailingOutputSchema:
        def __init__(self, **kwargs):
            raise ValueError("Output validation failed")

    class SchemaWithFailingOutput:
        input_schema = None
        output_schema = FailingOutputSchema
        name = "failing_output"

    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_output": SchemaWithFailingOutput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    afailing_output_method = proxy_cm.__dict__["afailing_output"]

    result = await afailing_output_method(param="value")
    assert result == {"result": "success"}


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_json_parsing_error(mock_httpx):
    """Test sync proxy method when JSON parsing fails."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = Exception("Invalid JSON")
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"json_error_endpoint": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    json_error_method = proxy_cm.__dict__["json_error_endpoint"]

    result = json_error_method(param="value")
    assert isinstance(result, DummyOutput)
    assert result.success is True


def test_getattr_raises_attribute_error():
    """Test that accessing unknown attributes raises AttributeError."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    with pytest.raises(AttributeError, match="'ProxyConnectionManager' object has no attribute 'nonexistent'"):
        _ = proxy_cm.nonexistent


@patch("httpx.AsyncClient")
@pytest.mark.asyncio
async def test_async_proxy_method_output_schema_no_validation(mock_client_class):
    """Test async proxy method when output_schema is None."""

    class SchemaWithoutOutputSchema:
        input_schema = None
        output_schema = None
        name = "no_output_schema"

    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "raw_result"}
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"no_output_schema": SchemaWithoutOutputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    ano_output_method = proxy_cm.__dict__["ano_output_schema"]

    result = await ano_output_method(param="value")
    assert result == {"result": "raw_result"}


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_output_schema_no_validation(mock_httpx):
    """Test sync proxy method when output_schema is None."""

    class SchemaWithoutOutputSchema:
        input_schema = None
        output_schema = None
        name = "no_output_schema"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "raw_result"}
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"no_output_schema": SchemaWithoutOutputSchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    no_output_method = proxy_cm.__dict__["no_output_schema"]

    result = no_output_method(param="value")
    assert result == {"result": "raw_result"}


@patch("mindtrace.services.gateway.proxy_connection_manager.httpx")
def test_sync_proxy_method_output_validation_error(mock_httpx):
    """Test sync proxy method when output validation fails."""

    class FailingOutputSchema:
        def __init__(self, **kwargs):
            raise ValueError("Output validation failed")

    class SchemaWithFailingOutput:
        input_schema = None
        output_schema = FailingOutputSchema
        name = "failing_output"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_httpx.post.return_value = mock_response

    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"failing_output": SchemaWithFailingOutput}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    failing_output_method = proxy_cm.__dict__["failing_output"]

    result = failing_output_method(param="value")
    assert result == {"result": "success"}


def test_proxy_method_access():
    """Test accessing proxy methods works normally."""
    dummy_cm = DummyCMWithServiceEndpoints()
    dummy_cm._service_endpoints = {"test_method": DummySchema}

    proxy_cm = ProxyConnectionManager(gateway_url="http://gateway", app_name="app", original_cm=dummy_cm)

    assert "test_method" in proxy_cm.__dict__
    assert "atest_method" in proxy_cm.__dict__

    sync_method = proxy_cm.test_method
    async_method = proxy_cm.atest_method

    assert callable(sync_method)
    assert callable(async_method)
    assert sync_method.__name__ == "test_method"
    assert async_method.__name__ == "atest_method"
