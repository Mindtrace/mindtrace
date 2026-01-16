"""Unit tests for the authentication module."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mindtrace.services.core.auth import (
    bearer_scheme,
    get_auth_dependency,
    get_token_verifier,
    set_token_verifier,
    verify_token,
)
from mindtrace.services.core.types import Scope


class TestTokenVerifier:
    """Test token verifier management functions."""

    def test_set_token_verifier_sync(self):
        """Test setting a synchronous token verifier."""

        def sync_verifier(token: str) -> dict:
            return {"user_id": "123", "email": "test@example.com"}

        set_token_verifier(sync_verifier)
        verifier = get_token_verifier()
        assert verifier == sync_verifier

    def test_set_token_verifier_async(self):
        """Test setting an asynchronous token verifier."""

        async def async_verifier(token: str) -> dict:
            return {"user_id": "456", "email": "async@example.com"}

        set_token_verifier(async_verifier)
        verifier = get_token_verifier()
        assert verifier == async_verifier

    def test_get_token_verifier_none(self):
        """Test getting token verifier when none is set."""
        # Reset verifier
        set_token_verifier(None)  # type: ignore
        verifier = get_token_verifier()
        assert verifier is None

    def test_set_token_verifier_overwrites(self):
        """Test that setting a new verifier overwrites the old one."""

        def verifier1(token: str) -> dict:
            return {"user_id": "1"}

        def verifier2(token: str) -> dict:
            return {"user_id": "2"}

        set_token_verifier(verifier1)
        assert get_token_verifier() == verifier1

        set_token_verifier(verifier2)
        assert get_token_verifier() == verifier2
        assert get_token_verifier() != verifier1


class TestVerifyToken:
    """Test the verify_token dependency function."""

    @pytest.mark.asyncio
    async def test_verify_token_no_credentials(self):
        """Test verify_token raises HTTPException when credentials are None."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated"
        assert "WWW-Authenticate" in exc_info.value.headers
        assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_verify_token_no_verifier(self):
        """Test verify_token with no verifier set (default behavior)."""
        # Reset verifier to None
        set_token_verifier(None)  # type: ignore

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "test_token_123"

        result = await verify_token(credentials=mock_credentials)

        assert result == {"token": "test_token_123", "authenticated": True}

    @pytest.mark.asyncio
    async def test_verify_token_sync_verifier_success(self):
        """Test verify_token with a synchronous verifier that succeeds."""

        def sync_verifier(token: str) -> dict:
            if token == "valid_token":
                return {"user_id": "123", "email": "test@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        set_token_verifier(sync_verifier)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_token"

        result = await verify_token(credentials=mock_credentials)

        assert result["user_id"] == "123"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_verify_token_sync_verifier_raises_http_exception(self):
        """Test verify_token when sync verifier raises HTTPException."""

        def sync_verifier(token: str) -> dict:
            raise HTTPException(status_code=401, detail="Token expired")

        set_token_verifier(sync_verifier)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "expired_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=mock_credentials)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token expired"

    @pytest.mark.asyncio
    async def test_verify_token_sync_verifier_raises_generic_exception(self):
        """Test verify_token when sync verifier raises a generic exception."""

        def sync_verifier(token: str) -> dict:
            raise ValueError("Unexpected error")

        set_token_verifier(sync_verifier)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "bad_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Token verification failed" in exc_info.value.detail
        assert "Unexpected error" in exc_info.value.detail
        assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_verify_token_async_verifier_success(self):
        """Test verify_token with an asynchronous verifier that succeeds."""

        async def async_verifier(token: str) -> dict:
            if token == "valid_async_token":
                return {"user_id": "456", "email": "async@example.com"}
            raise HTTPException(status_code=401, detail="Invalid token")

        set_token_verifier(async_verifier)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "valid_async_token"

        result = await verify_token(credentials=mock_credentials)

        assert result["user_id"] == "456"
        assert result["email"] == "async@example.com"

    @pytest.mark.asyncio
    async def test_verify_token_async_verifier_raises_http_exception(self):
        """Test verify_token when async verifier raises HTTPException."""

        async def async_verifier(token: str) -> dict:
            raise HTTPException(status_code=403, detail="Forbidden")

        set_token_verifier(async_verifier)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "forbidden_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=mock_credentials)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Forbidden"

    @pytest.mark.asyncio
    async def test_verify_token_async_verifier_raises_generic_exception(self):
        """Test verify_token when async verifier raises a generic exception."""

        async def async_verifier(token: str) -> dict:
            raise RuntimeError("Database connection failed")

        set_token_verifier(async_verifier)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.credentials = "error_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=mock_credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Token verification failed" in exc_info.value.detail
        assert "Database connection failed" in exc_info.value.detail


class TestGetAuthDependency:
    """Test the get_auth_dependency function."""

    def test_get_auth_dependency_authenticated(self):
        """Test get_auth_dependency returns Security dependency for AUTHENTICATED scope."""
        result = get_auth_dependency(Scope.AUTHENTICATED)

        assert result is not None
        # Verify it's a Security dependency (Security returns a Security object)
        # Check that it has the dependency attribute
        assert hasattr(result, "dependency")
        # The dependency should be the verify_token function
        assert callable(result.dependency)
        assert result.dependency is verify_token

    def test_get_auth_dependency_public(self):
        """Test get_auth_dependency returns None for PUBLIC scope."""
        result = get_auth_dependency(Scope.PUBLIC)

        assert result is None


class TestBearerScheme:
    """Test the bearer_scheme configuration."""

    def test_bearer_scheme_configuration(self):
        """Test that bearer_scheme is configured correctly."""
        assert isinstance(bearer_scheme, HTTPBearer)
        assert bearer_scheme.scheme_name == "Bearer"
        assert bearer_scheme.auto_error is False
        # HTTPBearer doesn't expose description directly, but it's set in the constructor
        # We can verify the scheme is properly configured by checking its attributes
        assert hasattr(bearer_scheme, "scheme_name")
