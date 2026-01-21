"""Unit tests for instance-based authentication in Service class."""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from mindtrace.services.core.service import Service
from mindtrace.services.core.types import Scope


class TestServiceTokenVerifier:
    """Test Service instance token verifier management."""

    def test_set_token_verifier_sync(self):
        """Test setting a synchronous token verifier on a service instance."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123", "email": "test@example.com"}

        service.set_token_verifier(sync_verifier)
        assert service.token_verifier == sync_verifier

    def test_set_token_verifier_async(self):
        """Test setting an asynchronous token verifier on a service instance."""
        service = Service()

        async def async_verifier(token: str) -> dict:
            return {"user_id": "456", "email": "async@example.com"}

        service.set_token_verifier(async_verifier)
        assert service.token_verifier == async_verifier

    def test_token_verifier_none_by_default(self):
        """Test that token_verifier is None by default."""
        service = Service()
        assert service.token_verifier is None

    def test_set_token_verifier_overwrites(self):
        """Test that setting a new verifier overwrites the old one."""
        service = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service.set_token_verifier(verifier1)
        assert service.token_verifier == verifier1

        service.set_token_verifier(verifier2)
        assert service.token_verifier == verifier2
        assert service.token_verifier != verifier1

    def test_token_verifier_per_instance(self):
        """Test that each service instance has its own token verifier."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service1.set_token_verifier(verifier1)
        service2.set_token_verifier(verifier2)

        assert service1.token_verifier == verifier1
        assert service2.token_verifier == verifier2
        assert service1.token_verifier != service2.token_verifier


class TestServiceVerifyTokenDependency:
    """Test the service-specific verify_token dependency function."""

    def test_create_verify_token_dependency_raises_without_verifier(self):
        """Test that get_current_user_dependency raises RuntimeError when no verifier is set."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_current_user_dependency()

        assert "Token verifier not set" in str(exc_info.value)
        assert "set_token_verifier" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_token_no_credentials(self):
        """Test verify_token raises HTTPException when credentials are None."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_token_verifier(sync_verifier)
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

        service.set_token_verifier(sync_verifier)
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

        service.set_token_verifier(sync_verifier)
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

        service.set_token_verifier(sync_verifier)
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

        service.set_token_verifier(async_verifier)
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

        service.set_token_verifier(async_verifier)
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

        service.set_token_verifier(async_verifier)
        verify_token_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "error_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Token verification failed"
        assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_verify_token_defensive_check_verifier_none(self):
        """Test the defensive check in verify_token when verifier becomes None after dependency creation.

        This tests line 642 - the defensive check that should never happen in practice,
        but protects against edge cases where the verifier is removed after dependency creation.
        """
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_token_verifier(sync_verifier)
        verify_token_fn = service.get_current_user_dependency()

        # Simulate verifier being removed after dependency creation (edge case)
        service.token_verifier = None

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "test_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token_fn(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Token verifier not configured" in exc_info.value.detail
        assert "WWW-Authenticate" in exc_info.value.headers


class TestServiceGetAuthDependency:
    """Test the Service.get_auth_dependency method."""

    def test_get_auth_dependency_authenticated_raises_without_verifier(self):
        """Test get_auth_dependency raises RuntimeError when no verifier is set for AUTHENTICATED scope."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_auth_dependency(Scope.AUTHENTICATED)

        assert "Token verifier not set" in str(exc_info.value)

    def test_get_auth_dependency_authenticated(self):
        """Test get_auth_dependency returns Security dependency for AUTHENTICATED scope."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_token_verifier(sync_verifier)
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
        """Test that get_auth_dependency uses the service instance's token verifier."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service1.set_token_verifier(verifier1)
        service2.set_token_verifier(verifier2)

        dep1 = service1.get_auth_dependency(Scope.AUTHENTICATED)
        dep2 = service2.get_auth_dependency(Scope.AUTHENTICATED)

        # Both should be Security dependencies
        assert dep1 is not None
        assert dep2 is not None
        # But they should use different verifiers (different service instances)
        assert dep1.dependency != dep2.dependency


class TestServiceGetCurrentUserDependency:
    """Test the Service.get_current_user_dependency method."""

    def test_get_current_user_dependency_raises_without_verifier(self):
        """Test get_current_user_dependency raises RuntimeError when no verifier is set."""
        service = Service()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_current_user_dependency()

        assert "Token verifier not set" in str(exc_info.value)

    def test_get_current_user_dependency_returns_callable(self):
        """Test get_current_user_dependency returns a callable dependency function."""
        service = Service()

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123"}

        service.set_token_verifier(sync_verifier)
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

        service.set_token_verifier(sync_verifier)
        dependency_fn = service.get_current_user_dependency()

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        result = await dependency_fn(credentials=mock_credentials)

        assert result["user_id"] == "123"
        assert result["email"] == "test@example.com"

    def test_get_current_user_dependency_per_instance(self):
        """Test that each service instance returns its own dependency function."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        service1.set_token_verifier(verifier1)
        service2.set_token_verifier(verifier2)

        dep1 = service1.get_current_user_dependency()
        dep2 = service2.get_current_user_dependency()

        # They should be different functions (bound to different instances)
        assert dep1 != dep2


class TestServiceAuthIntegration:
    """Integration tests for authentication in Service endpoints."""

    def test_add_endpoint_with_authenticated_scope_raises_without_verifier(self):
        """Test that adding authenticated endpoint without verifier raises RuntimeError."""
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

        assert "Token verifier not set" in str(exc_info.value)

    def test_add_endpoint_with_authenticated_scope_uses_instance_verifier(self):
        """Test that authenticated endpoints use the service instance's token verifier."""
        service = Service()

        def test_verifier(token: str) -> dict:
            return {"user_id": "test", "email": "test@example.com"}

        service.set_token_verifier(test_verifier)

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
        """Test that multiple service instances can have different token verifiers."""
        service1 = Service()
        service2 = Service()

        def verifier1(token: str) -> dict:
            return {"service": "1", "user_id": "123"}

        def verifier2(token: str) -> dict:
            return {"service": "2", "user_id": "456"}

        service1.set_token_verifier(verifier1)
        service2.set_token_verifier(verifier2)

        # Verify they have different verifiers
        assert service1.token_verifier == verifier1
        assert service2.token_verifier == verifier2

        # Verify their auth dependencies are different
        dep1 = service1.get_auth_dependency(Scope.AUTHENTICATED)
        dep2 = service2.get_auth_dependency(Scope.AUTHENTICATED)

        assert dep1 is not None
        assert dep2 is not None
        assert dep1.dependency != dep2.dependency
