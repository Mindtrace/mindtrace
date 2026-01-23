"""Unit tests for instance-based authentication in Service class."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from mindtrace.services.core.service import Service
from mindtrace.services.core.types import Scope


class TestServiceUserAuthenticator:
    """Test Service instance user authenticator management."""

    def test_set_user_authenticator_sync(self):
        """Test setting a synchronous user authenticator on a service instance."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123", "email": "test@example.com"}

        service.set_user_authenticator(sync_verifier)
        assert service.user_authenticator == sync_verifier

    def test_set_user_authenticator_async(self):
        """Test setting an asynchronous user authenticator on a service instance."""
        service = Service()

        async def async_verifier(token: str) -> dict:
            return {"user_id": "456", "email": "async@example.com"}

        service.set_user_authenticator(async_verifier)
        assert service.user_authenticator == async_verifier

    def test_set_user_authenticator_returns_none(self):
        """Test setting a verifier that returns None (lightweight verification only)."""
        service = Service()

        def lightweight_verifier(token: str) -> None:
            # Just verify, don't return user data
            return None

        service.set_user_authenticator(lightweight_verifier)
        assert service.user_authenticator == lightweight_verifier

    def test_user_authenticator_none_by_default(self):
        """Test that user_authenticator is None by default."""
        service = Service()
        assert service.user_authenticator is None

    def test_set_user_authenticator_overwrites(self):
        """Test that setting a new verifier overwrites the old one."""
        service = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service.set_user_authenticator(verifier1)
        assert service.user_authenticator == verifier1

        service.set_user_authenticator(verifier2)
        assert service.user_authenticator == verifier2
        assert service.user_authenticator != verifier1

    def test_user_authenticator_per_instance(self):
        """Test that each service instance has its own user authenticator."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service1.set_user_authenticator(verifier1)
        service2.set_user_authenticator(verifier2)

        assert service1.user_authenticator == verifier1
        assert service2.user_authenticator == verifier2
        assert service1.user_authenticator != service2.user_authenticator


class TestServiceGetUserDependency:
    """Test the get_user dependency function (returns user data)."""

    def test_get_user_dependency_raises_without_verifier(self):
        """Test that get_current_user_dependency raises RuntimeError when no authenticator is set."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_current_user_dependency()

        assert "User authenticator not set" in str(exc_info.value)
        assert "set_user_authenticator" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_token_no_credentials(self):
        """Test verify_token raises HTTPException when credentials are None."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_user_authenticator(sync_verifier)
        verify_token_fn = service.get_current_user_dependency()

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated"
        assert "WWW-Authenticate" in exc_info.value.headers
        assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_verify_token_sync_verifier_success(self):
        """Test verify_token with a synchronous verifier that succeeds."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            if token == "valid_token":
                return {"user_id": "123", "email": "test@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        service.set_user_authenticator(sync_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        result = await verify_token_fn(credentials=mock_credentials)

        assert result["user_id"] == "123"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_verify_token_sync_verifier_raises_http_exception(self):
        """Test verify_token when sync verifier raises HTTPException."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            raise HTTPException(status_code=401, detail="Token expired")

        service.set_user_authenticator(sync_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "expired_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token expired"

    @pytest.mark.asyncio
    async def test_verify_token_sync_verifier_raises_generic_exception(self):
        """Test verify_token when sync verifier raises a generic exception."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            raise ValueError("Unexpected error")

        service.set_user_authenticator(sync_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "bad_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Token verification failed"
        assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_verify_token_async_verifier_success(self):
        """Test verify_token with an asynchronous verifier that succeeds."""
        service = Service()

        async def async_verifier(token: str) -> dict:
            if token == "valid_async_token":
                return {"user_id": "456", "email": "async@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        service.set_user_authenticator(async_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_async_token"

        result = await verify_token_fn(credentials=mock_credentials)

        assert result["user_id"] == "456"
        assert result["email"] == "async@example.com"

    @pytest.mark.asyncio
    async def test_verify_token_async_verifier_raises_http_exception(self):
        """Test verify_token when async verifier raises HTTPException."""
        service = Service()

        async def async_verifier(token: str) -> dict:
            raise HTTPException(status_code=403, detail="Forbidden")

        service.set_user_authenticator(async_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "forbidden_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Forbidden"

    @pytest.mark.asyncio
    async def test_verify_token_async_verifier_raises_generic_exception(self):
        """Test verify_token when async verifier raises a generic exception."""
        service = Service()

        async def async_verifier(token: str) -> dict:
            raise RuntimeError("Database connection failed")

        service.set_user_authenticator(async_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "error_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Token verification failed"
        assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_get_user_defensive_check_authenticator_none(self):
        """Test the defensive check in get_user when authenticator becomes None after dependency creation.

        This tests the defensive check that should never happen in practice,
        but protects against edge cases where the authenticator is removed after dependency creation.
        """
        service = Service()

        def sync_authenticator(token: str) -> dict:
            return {"user_id": "123"}

        service.set_user_authenticator(sync_authenticator)
        get_user_fn = service.get_current_user_dependency()

        # Simulate authenticator being removed after dependency creation (edge case)
        service.user_authenticator = None

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "test_token"

        with pytest.raises(HTTPException) as exc_info:
            await get_user_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "User authenticator not configured" in exc_info.value.detail
        assert "WWW-Authenticate" in exc_info.value.headers


class TestServiceAuthOnlyDependency:
    """Test the lightweight auth-only dependency (for scope=Scope.AUTHENTICATED)."""

    def test_get_auth_dependency_raises_without_verifier(self):
        """Test that get_auth_dependency raises RuntimeError when no authenticator is set."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_auth_dependency(Scope.AUTHENTICATED)

        assert "User authenticator not set" in str(exc_info.value)
        assert "set_user_authenticator" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_auth_only_no_credentials(self):
        """Test auth-only dependency raises HTTPException when credentials are None."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_user_authenticator(sync_verifier)
        auth_dep = service.get_auth_dependency(Scope.AUTHENTICATED)
        auth_only_fn = auth_dep.dependency

        with pytest.raises(HTTPException) as exc_info:
            await auth_only_fn(credentials=None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated"
        assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_auth_only_verifies_but_returns_none(self):
        """Test auth-only dependency verifies token but returns None (no user data)."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            if token == "valid_token":
                return {"user_id": "123", "email": "test@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        service.set_user_authenticator(sync_verifier)
        auth_dep = service.get_auth_dependency(Scope.AUTHENTICATED)
        auth_only_fn = auth_dep.dependency

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        # Auth-only dependency should return None (not user data)
        result = await auth_only_fn(credentials=mock_credentials)
        assert result is None

    @pytest.mark.asyncio
    async def test_auth_only_async_verifier(self):
        """Test auth-only dependency works with async verifier."""
        service = Service()

        async def async_verifier(token: str) -> dict:
            if token == "valid_async_token":
                return {"user_id": "456", "email": "async@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        service.set_user_authenticator(async_verifier)
        auth_dep = service.get_auth_dependency(Scope.AUTHENTICATED)
        auth_only_fn = auth_dep.dependency

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_async_token"

        # Should return None (not user data)
        result = await auth_only_fn(credentials=mock_credentials)
        assert result is None

    @pytest.mark.asyncio
    async def test_auth_only_raises_on_invalid_token(self):
        """Test auth-only dependency raises HTTPException on invalid token."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            raise HTTPException(status_code=401, detail="Token expired")

        service.set_user_authenticator(sync_verifier)
        auth_dep = service.get_auth_dependency(Scope.AUTHENTICATED)
        auth_only_fn = auth_dep.dependency

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "expired_token"

        with pytest.raises(HTTPException) as exc_info:
            await auth_only_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token expired"


class TestServiceGetAuthDependency:
    """Test the Service.get_auth_dependency method."""

    def test_get_auth_dependency_authenticated_raises_without_verifier(self):
        """Test get_auth_dependency raises RuntimeError when no authenticator is set for AUTHENTICATED scope."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_auth_dependency(Scope.AUTHENTICATED)

        assert "User authenticator not set" in str(exc_info.value)

    def test_get_auth_dependency_authenticated(self):
        """Test get_auth_dependency returns Security dependency for AUTHENTICATED scope."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_user_authenticator(sync_verifier)
        result = service.get_auth_dependency(Scope.AUTHENTICATED)

        assert result is not None
        # Verify it's a Security dependency
        assert hasattr(result, "dependency")
        # The dependency should be callable
        assert callable(result.dependency)

    def test_get_auth_dependency_public(self):
        """Test get_auth_dependency returns None for PUBLIC scope."""
        service = Service()
        result = service.get_auth_dependency(Scope.PUBLIC)

        assert result is None

    def test_get_auth_dependency_uses_service_instance(self):
        """Test that get_auth_dependency uses the service instance's user authenticator."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service1.set_user_authenticator(verifier1)
        service2.set_user_authenticator(verifier2)

        dep1 = service1.get_auth_dependency(Scope.AUTHENTICATED)
        dep2 = service2.get_auth_dependency(Scope.AUTHENTICATED)

        # Both should be Security dependencies
        assert dep1 is not None
        assert dep2 is not None
        # But they should use different verifiers (different service instances)
        assert dep1.dependency != dep2.dependency

    def test_auth_dependency_different_from_user_dependency(self):
        """Test that auth-only dependency (verify_token) is different from user-data dependency (get_user)."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_user_authenticator(sync_verifier)

        # Auth dependency (for scope=Scope.AUTHENTICATED) - lightweight, returns None
        auth_dep = service.get_auth_dependency(Scope.AUTHENTICATED)
        verify_token_fn = auth_dep.dependency

        # User dependency (for get_current_user_dependency) - returns user dict
        get_user_fn = service.get_current_user_dependency()

        # They should be different functions
        assert verify_token_fn != get_user_fn


class TestServiceGetCurrentUserDependency:
    """Test the Service.get_current_user_dependency method."""

    def test_get_current_user_dependency_raises_without_verifier(self):
        """Test get_current_user_dependency raises RuntimeError when no authenticator is set."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_current_user_dependency()

        assert "User authenticator not set" in str(exc_info.value)

    def test_get_current_user_dependency_returns_callable(self):
        """Test get_current_user_dependency returns a callable dependency function."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_user_authenticator(sync_verifier)
        dependency_fn = service.get_current_user_dependency()

        assert callable(dependency_fn)

    @pytest.mark.asyncio
    async def test_get_current_user_dependency_uses_service_verifier(self):
        """Test that get_current_user_dependency uses the service instance's verifier."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            if token == "valid_token":
                return {"user_id": "123", "email": "test@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        service.set_user_authenticator(sync_verifier)
        dependency_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        result = await dependency_fn(credentials=mock_credentials)

        assert result["user_id"] == "123"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_dependency_raises_when_verifier_returns_none(self):
        """Test get_current_user_dependency raises HTTPException when verifier returns None."""
        service = Service()

        def lightweight_verifier(token: str) -> None:
            # Just verify, don't return user data
            return None

        service.set_user_authenticator(lightweight_verifier)
        get_user_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        with pytest.raises(HTTPException) as exc_info:
            await get_user_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "returned None" in exc_info.value.detail
        assert "get_current_user_dependency" in exc_info.value.detail

    def test_get_current_user_dependency_per_instance(self):
        """Test that each service instance returns its own dependency function."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service1.set_user_authenticator(verifier1)
        service2.set_user_authenticator(verifier2)

        dep1 = service1.get_current_user_dependency()
        dep2 = service2.get_current_user_dependency()

        # They should be different functions (bound to different instances)
        assert dep1 != dep2


class TestServiceAuthIntegration:
    """Integration tests for authentication in Service endpoints."""

    def test_add_endpoint_with_authenticated_scope_raises_without_verifier(self):
        """Test that adding authenticated endpoint without authenticator raises RuntimeError."""
        service = Service()

        def test_handler():
            return {"test": "response"}

        from mindtrace.core import TaskSchema

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=None)

        with pytest.raises(RuntimeError) as exc_info:
            service.add_endpoint(
                "test",
                test_handler,
                schema=test_schema,
                scope=Scope.AUTHENTICATED,
            )

        assert "User authenticator not set" in str(exc_info.value)

    def test_add_endpoint_with_authenticated_scope_uses_instance_verifier(self):
        """Test that authenticated endpoints use the service instance's user authenticator."""
        service = Service()

        def test_verifier(token: str) -> dict:
            return {"user_id": "test", "email": "test@example.com"}

        service.set_user_authenticator(test_verifier)

        def test_handler():
            return {"test": "response"}

        from mindtrace.core import TaskSchema

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
            # Verify it's a Security dependency
            assert any(hasattr(dep, "dependency") for dep in dependencies)

    def test_multiple_services_different_verifiers(self):
        """Test that multiple service instances can have different user authenticators."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"service": "1", "user_id": "123"}

        def verifier2(token: str) -> dict:
            return {"service": "2", "user_id": "456"}

        service1.set_user_authenticator(verifier1)
        service2.set_user_authenticator(verifier2)

        # Verify they have different verifiers
        assert service1.user_authenticator == verifier1
        assert service2.user_authenticator == verifier2

        # Verify their auth dependencies are different
        dep1 = service1.get_auth_dependency(Scope.AUTHENTICATED)
        dep2 = service2.get_auth_dependency(Scope.AUTHENTICATED)

        assert dep1 is not None
        assert dep2 is not None
        assert dep1.dependency != dep2.dependency


class TestConnectionManagerHeaders:
    """Test ConnectionManager header functionality for authentication."""

    def test_set_default_headers(self):
        """Test setting default headers on ConnectionManager."""
        from urllib3.util.url import parse_url

        from mindtrace.services.core.connection_manager import ConnectionManager

        cm = ConnectionManager(url=parse_url("http://test.com"))
        # Use getattr to avoid protected member warning
        assert getattr(cm, "_default_headers", {}) == {}

        cm.set_default_headers({"Authorization": "Bearer token123"})
        assert getattr(cm, "_default_headers") == {"Authorization": "Bearer token123"}

        # Setting again should update
        cm.set_default_headers({"Authorization": "Bearer token456", "X-Custom": "value"})
        assert getattr(cm, "_default_headers") == {"Authorization": "Bearer token456", "X-Custom": "value"}

    def test_clear_default_headers(self):
        """Test clearing default headers."""
        from urllib3.util.url import parse_url

        from mindtrace.services.core.connection_manager import ConnectionManager

        cm = ConnectionManager(url=parse_url("http://test.com"))
        cm.set_default_headers({"Authorization": "Bearer token123"})
        assert getattr(cm, "_default_headers") != {}

        cm.clear_default_headers()
        assert getattr(cm, "_default_headers") == {}

    def test_default_headers_inherited_by_generated_connection_manager(self):
        """Test that generated connection managers inherit default headers functionality."""
        from pydantic import BaseModel
        from urllib3.util.url import parse_url

        from mindtrace.core import TaskSchema
        from mindtrace.services.core.service import Service
        from mindtrace.services.core.utils import generate_connection_manager

        class TestOutput(BaseModel):
            result: str

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=TestOutput)

        class TestService(Service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.add_endpoint("test", self.test_handler, schema=test_schema)

            def test_handler(self):
                return TestOutput(result="ok")

        # Generate connection manager
        ConnectionManagerClass = generate_connection_manager(TestService)
        cm = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Should have default headers functionality
        assert hasattr(cm, "set_default_headers")
        assert hasattr(cm, "clear_default_headers")
        assert getattr(cm, "_default_headers", {}) == {}

        # Set default headers
        cm.set_default_headers({"Authorization": "Bearer token123"})
        assert getattr(cm, "_default_headers") == {"Authorization": "Bearer token123"}

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_includes_default_headers(self, mock_httpx):
        """Test that generated methods include default headers in requests."""
        from pydantic import BaseModel
        from urllib3.util.url import parse_url

        from mindtrace.core import TaskSchema
        from mindtrace.services.core.service import Service
        from mindtrace.services.core.utils import generate_connection_manager

        class TestOutput(BaseModel):
            result: str

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=TestOutput)

        class TestService(Service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.add_endpoint("test", self.test_handler, schema=test_schema)

            def test_handler(self):
                return TestOutput(result="ok")

        ConnectionManagerClass = generate_connection_manager(TestService)
        cm = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Set default headers
        cm.set_default_headers({"Authorization": "Bearer token123"})

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_httpx.post.return_value = mock_response

        # Call method
        cm.test()

        # Verify headers were included
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args[1]
        assert "headers" in call_kwargs
        assert call_kwargs["headers"] == {"Authorization": "Bearer token123"}

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_per_request_headers(self, mock_httpx):
        """Test that per-request headers override default headers."""
        from pydantic import BaseModel
        from urllib3.util.url import parse_url

        from mindtrace.core import TaskSchema
        from mindtrace.services.core.service import Service
        from mindtrace.services.core.utils import generate_connection_manager

        class TestOutput(BaseModel):
            result: str

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=TestOutput)

        class TestService(Service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.add_endpoint("test", self.test_handler, schema=test_schema)

            def test_handler(self):
                return TestOutput(result="ok")

        ConnectionManagerClass = generate_connection_manager(TestService)
        cm = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Set default headers
        cm.set_default_headers({"Authorization": "Bearer default_token", "X-Custom": "default"})

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_httpx.post.return_value = mock_response

        # Call method with per-request headers
        cm.test(headers={"Authorization": "Bearer per_request_token"})

        # Verify per-request headers override defaults
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args[1]
        assert "headers" in call_kwargs
        # Per-request should override default, but default X-Custom should remain
        assert call_kwargs["headers"]["Authorization"] == "Bearer per_request_token"
        assert call_kwargs["headers"]["X-Custom"] == "default"

    @patch("mindtrace.services.core.utils.httpx")
    def test_generated_method_no_headers_when_empty(self, mock_httpx):
        """Test that headers parameter is not included when no headers are set (backward compatibility)."""
        from pydantic import BaseModel
        from urllib3.util.url import parse_url

        from mindtrace.core import TaskSchema
        from mindtrace.services.core.service import Service
        from mindtrace.services.core.utils import generate_connection_manager

        class TestOutput(BaseModel):
            result: str

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=TestOutput)

        class TestService(Service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.add_endpoint("test", self.test_handler, schema=test_schema)

            def test_handler(self):
                return TestOutput(result="ok")

        ConnectionManagerClass = generate_connection_manager(TestService)
        cm = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_httpx.post.return_value = mock_response

        # Call method without headers
        cm.test()

        # Verify headers parameter is not included (backward compatibility)
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args[1]
        assert "headers" not in call_kwargs

    @patch("mindtrace.services.core.utils.httpx")
    @pytest.mark.asyncio
    async def test_generated_async_method_includes_default_headers(self, mock_httpx):
        """Test that generated async methods include default headers in requests."""
        from pydantic import BaseModel
        from urllib3.util.url import parse_url

        from mindtrace.core import TaskSchema
        from mindtrace.services.core.service import Service
        from mindtrace.services.core.utils import generate_connection_manager

        class TestOutput(BaseModel):
            result: str

        test_schema = TaskSchema(name="test", input_schema=None, output_schema=TestOutput)

        class TestService(Service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.add_endpoint("test", self.test_handler, schema=test_schema)

            def test_handler(self):
                return TestOutput(result="ok")

        ConnectionManagerClass = generate_connection_manager(TestService)
        cm = ConnectionManagerClass(url=parse_url("http://test.com"))

        # Set default headers
        cm.set_default_headers({"Authorization": "Bearer token123"})

        # Setup mock async client
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_client.post.return_value = mock_response
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        # Call async method
        await cm.atest()

        # Verify headers were included
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert "headers" in call_kwargs
        assert call_kwargs["headers"] == {"Authorization": "Bearer token123"}
