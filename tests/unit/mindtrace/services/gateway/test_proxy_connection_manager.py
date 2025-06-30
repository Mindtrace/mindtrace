import pytest
from unittest.mock import Mock, patch, PropertyMock
import inspect

import requests
from urllib3.util.url import Url

from mindtrace.services.gateway.proxy_connection_manager import ProxyConnectionManager
from mindtrace.services.core.connection_manager import ConnectionManager


class TestProxyConnectionManagerInitialization:
    """Test ProxyConnectionManager initialization and basic attribute access."""

    @pytest.fixture
    def mock_original_cm(self):
        """Create a mock original connection manager."""
        return Mock(spec=ConnectionManager)

    def test_init_with_string_url(self, mock_original_cm):
        """Test initialization with string URL."""
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=mock_original_cm
        )
        
        assert proxy.gateway_url == "http://localhost:8090"
        assert proxy.app_name == "test-service"
        assert proxy.original_cm == mock_original_cm

    def test_init_with_trailing_slash_removal(self, mock_original_cm):
        """Test that trailing slashes are removed from gateway URL."""
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090/",
            app_name="test-service",
            original_cm=mock_original_cm
        )
        
        assert proxy.gateway_url == "http://localhost:8090"

    def test_init_with_url_object(self, mock_original_cm):
        """Test initialization with Url object."""
        url = Url(scheme="http", host="localhost", port=8090, path="/")
        proxy = ProxyConnectionManager(
            gateway_url=url,
            app_name="test-service",
            original_cm=mock_original_cm
        )
        
        assert proxy.gateway_url == "http://localhost:8090"

    def test_init_with_multiple_trailing_slashes(self, mock_original_cm):
        """Test removal of multiple trailing slashes."""
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090///",
            app_name="test-service", 
            original_cm=mock_original_cm
        )
        
        assert proxy.gateway_url == "http://localhost:8090"

    def test_direct_attribute_access(self, mock_original_cm):
        """Test direct access to internal attributes."""
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=mock_original_cm
        )
        
        # These should access internal attributes directly
        assert proxy.gateway_url == "http://localhost:8090"
        assert proxy.app_name == "test-service"
        assert proxy.original_cm == mock_original_cm


class TestProxyConnectionManagerPropertyAccess:
    """Test property access through the proxy."""

    @pytest.fixture
    def mock_original_cm(self):
        """Create a mock with properties."""
        # Create a custom class with actual properties
        class MockConnectionManager:
            @property
            def status(self):
                return "available"
            
            @property
            def url(self):
                return "http://service:8001"
                
            # Add a regular method for comparison
            def echo(self):
                return "test"
        
        return MockConnectionManager()

    @pytest.fixture
    def proxy(self, mock_original_cm):
        """Create a ProxyConnectionManager instance."""
        return ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=mock_original_cm
        )

    def test_property_access_success(self, proxy, mock_original_cm):
        """Test successful property access through gateway."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "available"}
            mock_get.return_value = mock_response
            
            # Access a property that exists on the original CM
            result = proxy.status
            
            # Verify the GET request was made to the correct endpoint
            mock_get.assert_called_once_with(
                "http://localhost:8090/test-service/status",
                timeout=60
            )
            assert result == {"status": "available"}

    def test_property_access_failure(self, proxy, mock_original_cm):
        """Test property access failure."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Property not found"
            mock_get.return_value = mock_response
            
            # Access a property that exists on the original CM
            with pytest.raises(RuntimeError) as exc_info:
                proxy.status
            
            assert "Failed to get property 'status': Property not found" in str(exc_info.value)

    def test_non_property_attribute_fallback(self, proxy, mock_original_cm):
        """Test that non-property attributes fall back to __getattr__."""
        # Add a regular method to the mock
        mock_original_cm.echo = Mock(return_value="test")
        
        # Accessing a method should fall back to __getattr__ and return a proxy method
        result = proxy.echo
        
        # Should return a callable (the proxy method)
        assert callable(result)


class TestProxyConnectionManagerMethodProxying:
    """Test method call proxying through the gateway."""

    @pytest.fixture
    def mock_original_cm(self):
        """Create a mock with various methods."""
        mock_cm = Mock(spec=ConnectionManager)
        
        # Method that requires arguments
        def echo_method(message, delay=0.0):
            return {"echoed": message, "delay": delay}
        mock_cm.echo = echo_method
        
        # Method with no required arguments
        def status_method():
            return {"status": "ok"}
        mock_cm.status = status_method
        
        # Method with optional arguments only
        def heartbeat_method(detailed=False):
            return {"heartbeat": "ok", "detailed": detailed}
        mock_cm.heartbeat = heartbeat_method
        
        return mock_cm

    @pytest.fixture
    def proxy(self, mock_original_cm):
        """Create a ProxyConnectionManager instance."""
        return ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=mock_original_cm
        )

    def test_method_with_required_args_post(self, proxy):
        """Test method call with required arguments uses POST."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"echoed": "hello"}
            mock_post.return_value = mock_response
            
            # Call method with arguments
            result = proxy.echo(message="hello", delay=1.0)
            
            # Should use POST with JSON payload
            mock_post.assert_called_once_with(
                "http://localhost:8090/test-service/echo",
                json={"message": "hello", "delay": 1.0},
                timeout=60
            )
            assert result == {"echoed": "hello"}

    def test_method_with_no_required_args_get(self, proxy):
        """Test method call with no required arguments uses GET."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_get.return_value = mock_response
            
            # Call method with no arguments
            result = proxy.status()
            
            # Should use GET
            mock_get.assert_called_once_with(
                "http://localhost:8090/test-service/status",
                timeout=60
            )
            assert result == {"status": "ok"}

    def test_method_with_optional_args_only_get(self, proxy):
        """Test method with only optional arguments uses GET."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"heartbeat": "ok"}
            mock_get.return_value = mock_response
            
            # Call method without providing optional arguments
            result = proxy.heartbeat()
            
            # Should use GET since no required arguments
            mock_get.assert_called_once_with(
                "http://localhost:8090/test-service/heartbeat",
                timeout=60
            )
            assert result == {"heartbeat": "ok"}

    def test_method_with_positional_args(self, proxy):
        """Test method call with positional arguments."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"echoed": "hello"}
            mock_post.return_value = mock_response
            
            # Call method with positional argument
            result = proxy.echo("hello")
            
            # Should use first positional argument as payload
            mock_post.assert_called_once_with(
                "http://localhost:8090/test-service/echo",
                json="hello",
                timeout=60
            )
            assert result == {"echoed": "hello"}

    def test_method_with_no_args_but_required_params(self, proxy):
        """Test method call with no args provided but method has required params."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"echoed": ""}
            mock_post.return_value = mock_response
            
            # Call method that requires args but don't provide any
            result = proxy.echo()
            
            # Should use POST with empty dict payload
            mock_post.assert_called_once_with(
                "http://localhost:8090/test-service/echo",
                json={},
                timeout=60
            )
            assert result == {"echoed": ""}

    def test_method_prefers_kwargs_over_args(self, proxy):
        """Test that kwargs are preferred over positional args for payload."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"echoed": "from_kwargs"}
            mock_post.return_value = mock_response
            
            # Call method with both args and kwargs
            result = proxy.echo("from_args", message="from_kwargs")
            
            # Should use kwargs as payload
            mock_post.assert_called_once_with(
                "http://localhost:8090/test-service/echo",
                json={"message": "from_kwargs"},
                timeout=60
            )
            assert result == {"echoed": "from_kwargs"}


class TestProxyConnectionManagerErrorHandling:
    """Test error handling in ProxyConnectionManager."""

    @pytest.fixture
    def mock_original_cm(self):
        """Create a mock connection manager."""
        mock_cm = Mock(spec=['echo', 'status'])
        mock_cm.echo = Mock(return_value={"echoed": "test"})
        return mock_cm

    @pytest.fixture
    def proxy(self, mock_original_cm):
        """Create a ProxyConnectionManager instance."""
        return ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=mock_original_cm
        )

    def test_nonexistent_method_error(self, proxy):
        """Test accessing a method that doesn't exist on original CM."""
        with pytest.raises(AttributeError) as exc_info:
            proxy.nonexistent_method()
        
        assert "has no attribute 'nonexistent_method'" in str(exc_info.value)

    def test_non_callable_attribute_error(self, proxy, mock_original_cm):
        """Test accessing a non-callable attribute."""
        # Add a non-callable attribute
        mock_original_cm.some_value = "not_callable"
        
        with pytest.raises(AttributeError) as exc_info:
            proxy.some_value()
        
        assert "has no callable attribute 'some_value'" in str(exc_info.value)

    def test_http_error_response(self, proxy):
        """Test handling of HTTP error responses."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response
            
            with pytest.raises(RuntimeError) as exc_info:
                proxy.echo(message="test")
            
            assert "Gateway proxy request failed: Internal Server Error" in str(exc_info.value)

    def test_network_error(self, proxy):
        """Test handling of network errors."""
        with patch('requests.post', side_effect=requests.ConnectionError("Network error")):
            with pytest.raises(requests.ConnectionError):
                proxy.echo(message="test")

    def test_property_access_network_error(self):
        """Test network error during property access."""
        # Create a mock with a real property
        class MockCMWithProperty:
            @property
            def status(self):
                return "available"
        
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=MockCMWithProperty()
        )
        
        with patch('requests.get', side_effect=requests.ConnectionError("Network error")):
            with pytest.raises(requests.ConnectionError):
                proxy.status


class TestProxyConnectionManagerEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.fixture
    def mock_original_cm(self):
        """Create a mock with various method signatures."""
        mock_cm = Mock()
        
        # Method with *args and **kwargs
        def flexible_method(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}
        mock_cm.flexible = flexible_method
        
        # Method with mixed parameters
        def mixed_method(required, optional="default", *args, **kwargs):
            return {"required": required, "optional": optional, "args": args, "kwargs": kwargs}
        mock_cm.mixed = mixed_method
        
        return mock_cm

    @pytest.fixture
    def proxy(self, mock_original_cm):
        """Create a ProxyConnectionManager instance."""
        return ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service",
            original_cm=mock_original_cm
        )

    def test_method_with_args_kwargs(self, proxy):
        """Test method with *args and **kwargs signature."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_post.return_value = mock_response
            
            # Call flexible method with kwargs
            result = proxy.flexible(key="value", another="param")
            
            # Should use POST with kwargs as payload
            mock_post.assert_called_once_with(
                "http://localhost:8090/test-service/flexible",
                json={"key": "value", "another": "param"},
                timeout=60
            )

    def test_method_with_mixed_signature(self, proxy):
        """Test method with mixed parameter types."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_post.return_value = mock_response
            
            # This method has required parameters, so should use POST
            result = proxy.mixed(required="test", optional="custom")
            
            mock_post.assert_called_once_with(
                "http://localhost:8090/test-service/mixed",
                json={"required": "test", "optional": "custom"},
                timeout=60
            )

    def test_gateway_url_with_path(self, mock_original_cm):
        """Test gateway URL that includes a path."""
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090/api/v1/",
            app_name="test-service",
            original_cm=mock_original_cm
        )
        
        assert proxy.gateway_url == "http://localhost:8090/api/v1"

    def test_complex_app_name(self, mock_original_cm):
        """Test with complex app name containing special characters."""
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test-service-v2",
            original_cm=mock_original_cm
        )
        
        assert proxy.app_name == "test-service-v2"
        
        # Test that the app name is used correctly in URLs
        mock_original_cm.echo = Mock()
        
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_post.return_value = mock_response
            
            proxy.echo(message="test")
            
            expected_url = "http://localhost:8090/test-service-v2/echo"
            mock_post.assert_called_once_with(
                expected_url,
                json={"message": "test"},
                timeout=60
            )


class TestProxyConnectionManagerIntegration:
    """Integration tests that test the full proxy workflow."""

    def test_full_proxy_workflow(self):
        """Test the complete proxy workflow from initialization to method call."""
        # Create a realistic mock connection manager
        original_cm = Mock(spec=ConnectionManager)
        
        # Add a method with specific signature
        def echo_method(message: str, delay: float = 0.0):
            return {"echoed": message, "delay": delay}
        original_cm.echo = echo_method
        
        # Create proxy
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090/",  # With trailing slash
            app_name="echo-service",
            original_cm=original_cm
        )
        
        # Verify initialization
        assert proxy.gateway_url == "http://localhost:8090"
        assert proxy.app_name == "echo-service"
        assert proxy.original_cm == original_cm
        
        # Test method call
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"echoed": "hello world", "delay": 0.5}
            mock_post.return_value = mock_response
            
            result = proxy.echo(message="hello world", delay=0.5)
            
            # Verify request
            mock_post.assert_called_once_with(
                "http://localhost:8090/echo-service/echo",
                json={"message": "hello world", "delay": 0.5},
                timeout=60
            )
            
            # Verify response
            assert result == {"echoed": "hello world", "delay": 0.5}

    def test_method_signature_analysis(self):
        """Test that method signature analysis works correctly."""
        original_cm = Mock()
        
        # Method with no required parameters
        def no_required_params(optional="default"):
            return {"optional": optional}
        original_cm.no_required = no_required_params
        
        # Method with required parameters
        def required_params(required, optional="default"):
            return {"required": required, "optional": optional}
        original_cm.required = required_params
        
        proxy = ProxyConnectionManager(
            gateway_url="http://localhost:8090",
            app_name="test",
            original_cm=original_cm
        )
        
        # Test no required params -> GET
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"optional": "default"}
            mock_get.return_value = mock_response
            
            proxy.no_required()
            mock_get.assert_called_once()
        
        # Test required params -> POST
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"required": "test", "optional": "default"}
            mock_post.return_value = mock_response
            
            proxy.required(required="test")
            mock_post.assert_called_once()
