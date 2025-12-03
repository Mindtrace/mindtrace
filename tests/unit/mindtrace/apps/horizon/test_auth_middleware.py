"""Unit tests for Horizon AuthMiddleware."""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from mindtrace.apps.horizon.auth_middleware import AuthMiddleware


class TestAuthMiddlewareInit:
    """Tests for AuthMiddleware initialization."""

    def test_init_default_values(self):
        """Test AuthMiddleware has sensible defaults."""
        app = MagicMock()
        middleware = AuthMiddleware(app)

        assert middleware.secret_key == "dev-secret-key"
        assert middleware.enabled is False
        assert "/status" in middleware.bypass_paths
        assert "/heartbeat" in middleware.bypass_paths
        assert "/endpoints" in middleware.bypass_paths

    def test_init_custom_values(self):
        """Test AuthMiddleware accepts custom values."""
        app = MagicMock()
        middleware = AuthMiddleware(
            app,
            secret_key="custom-key",
            enabled=True,
            bypass_paths={"/health", "/custom"},
        )

        assert middleware.secret_key == "custom-key"
        assert middleware.enabled is True
        assert middleware.bypass_paths == {"/health", "/custom"}


class TestAuthMiddlewareDispatch:
    """Tests for AuthMiddleware dispatch logic."""

    @pytest.fixture
    def middleware(self):
        """Create a middleware instance for testing."""
        app = MagicMock()
        return AuthMiddleware(app, secret_key="test-secret", enabled=True)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock()
        request.url.path = "/some-endpoint"
        request.headers = {}
        return request

    @pytest.fixture
    def mock_call_next(self):
        """Create a mock call_next function."""
        response = MagicMock()
        response.status_code = 200
        return AsyncMock(return_value=response)

    @pytest.mark.asyncio
    async def test_dispatch_disabled_passes_through(self, mock_request, mock_call_next):
        """Test that disabled middleware passes requests through."""
        app = MagicMock()
        middleware = AuthMiddleware(app, enabled=False)

        response = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_bypass_path_passes_through(self, middleware, mock_call_next):
        """Test that bypass paths don't require authentication."""
        request = MagicMock()
        request.url.path = "/status"
        request.headers = {}

        response = await middleware.dispatch(request, mock_call_next)

        mock_call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_bypass_path_with_trailing_slash(self, middleware, mock_call_next):
        """Test that bypass paths work with trailing slash."""
        request = MagicMock()
        request.url.path = "/status/"
        request.headers = {}

        response = await middleware.dispatch(request, mock_call_next)

        mock_call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_missing_auth_header_returns_401(self, middleware, mock_request, mock_call_next):
        """Test that missing Authorization header returns 401."""
        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 401
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_invalid_auth_format_returns_401(self, middleware, mock_request, mock_call_next):
        """Test that invalid Authorization format returns 401."""
        mock_request.headers = {"Authorization": "InvalidFormat"}

        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_dispatch_invalid_token_returns_403(self, middleware, mock_request, mock_call_next):
        """Test that invalid token returns 403."""
        mock_request.headers = {"Authorization": "Bearer invalid-token"}

        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_dispatch_dev_token_passes(self, middleware, mock_request, mock_call_next):
        """Test that dev-token passes validation."""
        mock_request.headers = {"Authorization": "Bearer dev-token"}

        response = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_valid_hmac_token_passes(self, middleware, mock_request, mock_call_next):
        """Test that valid HMAC token passes validation."""
        timestamp = str(int(time.time()))
        signature = hmac.new(
            b"test-secret",
            timestamp.encode(),
            hashlib.sha256,
        ).hexdigest()
        token = f"{timestamp}.{signature}"

        mock_request.headers = {"Authorization": f"Bearer {token}"}

        response = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_mcp_server_prefix_bypassed(self, middleware, mock_call_next):
        """Test that /mcp-server/* paths are bypassed."""
        request = MagicMock()
        request.url.path = "/mcp-server/some/path"
        request.headers = {}

        response = await middleware.dispatch(request, mock_call_next)

        mock_call_next.assert_called_once_with(request)


class TestAuthMiddlewareTokenValidation:
    """Tests for AuthMiddleware token validation."""

    @pytest.fixture
    def middleware(self):
        """Create a middleware instance for testing."""
        app = MagicMock()
        return AuthMiddleware(app, secret_key="test-secret", enabled=True)

    def test_validate_token_dev_token(self, middleware):
        """Test dev-token is valid."""
        assert middleware._validate_token("dev-token") is True

    def test_validate_token_invalid_format(self, middleware):
        """Test invalid format fails."""
        assert middleware._validate_token("no-dot-in-token") is False

    def test_validate_token_invalid_timestamp(self, middleware):
        """Test invalid timestamp fails."""
        assert middleware._validate_token("not-a-number.signature") is False

    def test_validate_token_wrong_signature(self, middleware):
        """Test wrong signature fails."""
        timestamp = str(int(time.time()))
        assert middleware._validate_token(f"{timestamp}.wrong-signature") is False

    def test_validate_token_valid_signature(self, middleware):
        """Test valid signature passes."""
        timestamp = str(int(time.time()))
        signature = hmac.new(
            b"test-secret",
            timestamp.encode(),
            hashlib.sha256,
        ).hexdigest()

        assert middleware._validate_token(f"{timestamp}.{signature}") is True


class TestAuthMiddlewareGenerateToken:
    """Tests for AuthMiddleware.generate_token class method."""

    def test_generate_token_format(self):
        """Test generated token has correct format."""
        timestamp = 1234567890
        token = AuthMiddleware.generate_token("secret", timestamp)

        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2
        assert parts[0] == "1234567890"

    def test_generate_token_verifiable(self):
        """Test generated token can be verified."""
        secret = "my-secret-key"
        timestamp = int(time.time())
        token = AuthMiddleware.generate_token(secret, timestamp)

        # Create middleware with same secret and verify
        app = MagicMock()
        middleware = AuthMiddleware(app, secret_key=secret, enabled=True)

        assert middleware._validate_token(token) is True

    def test_generate_token_different_secrets_fail(self):
        """Test token generated with different secret fails verification."""
        timestamp = int(time.time())
        token = AuthMiddleware.generate_token("secret-a", timestamp)

        app = MagicMock()
        middleware = AuthMiddleware(app, secret_key="secret-b", enabled=True)

        assert middleware._validate_token(token) is False

