"""Unit tests for auth middleware."""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from mindtrace.apps.inspectra.core.auth_middleware import AUTH_EXEMPT_PATHS, AuthMiddleware


@dataclass
class _FakeUser:
    id: str
    username: str
    role_id: str
    plant_id: Optional[str] = None
    is_active: bool = True


@dataclass
class _FakeRole:
    id: str
    name: str
    permissions: list = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


class TestAuthMiddlewareExemptPaths:
    """Tests for exempt path handling."""

    @pytest.mark.asyncio
    async def test_auth_login_is_exempt(self):
        """Auth login path should bypass authentication."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/auth/login"
        request.method = "POST"

        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_auth_register_is_exempt(self):
        """Auth register path should bypass authentication."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/auth/register"
        request.method = "POST"

        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_docs_is_exempt(self):
        """Docs path should bypass authentication."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/docs"
        request.method = "GET"

        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_options_request_bypasses_auth(self):
        """OPTIONS requests should bypass authentication (CORS preflight)."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "OPTIONS"

        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)


class TestAuthMiddlewareAuthentication:
    """Tests for authentication handling."""

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises_401(self):
        """Missing Authorization header should raise 401."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {}

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await middleware.dispatch(request, call_next)

        assert exc.value.status_code == 401
        assert "Not authenticated" in exc.value.detail

    @pytest.mark.asyncio
    async def test_invalid_auth_format_raises_401(self):
        """Authorization header without Bearer prefix should raise 401."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {"Authorization": "Basic abc123"}

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await middleware.dispatch(request, call_next)

        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Invalid JWT token should raise 401."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer invalid_token"}

        call_next = AsyncMock()

        with patch(
            "mindtrace.apps.inspectra.core.security.decode_token"
        ) as mock_decode:
            mock_decode.side_effect = HTTPException(status_code=401, detail="Invalid token")

            with pytest.raises(HTTPException) as exc:
                await middleware.dispatch(request, call_next)

            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self):
        """User not found should raise 401."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer valid_token"}

        call_next = AsyncMock()

        mock_token_data = MagicMock()
        mock_token_data.sub = "nonexistent_user"

        with patch(
            "mindtrace.apps.inspectra.core.security.decode_token"
        ) as mock_decode, patch(
            "mindtrace.apps.inspectra.repositories.user_repository.UserRepository"
        ) as mock_repo_class:
            mock_decode.return_value = mock_token_data

            mock_repo = AsyncMock()
            mock_repo.get_by_username.return_value = None
            mock_repo_class.return_value = mock_repo

            with pytest.raises(HTTPException) as exc:
                await middleware.dispatch(request, call_next)

            assert exc.value.status_code == 401
            assert "User not found" in exc.value.detail

    @pytest.mark.asyncio
    async def test_deactivated_user_raises_403(self):
        """Deactivated user should raise 403."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer valid_token"}

        call_next = AsyncMock()

        mock_token_data = MagicMock()
        mock_token_data.sub = "deactivated_user"

        mock_user = _FakeUser(
            id="user123",
            username="deactivated_user",
            role_id="role456",
            is_active=False,
        )

        with patch(
            "mindtrace.apps.inspectra.core.security.decode_token"
        ) as mock_decode, patch(
            "mindtrace.apps.inspectra.repositories.user_repository.UserRepository"
        ) as mock_repo_class:
            mock_decode.return_value = mock_token_data

            mock_repo = AsyncMock()
            mock_repo.get_by_username.return_value = mock_user
            mock_repo_class.return_value = mock_repo

            with pytest.raises(HTTPException) as exc:
                await middleware.dispatch(request, call_next)

            assert exc.value.status_code == 403
            assert "deactivated" in exc.value.detail.lower()


class TestAuthMiddlewareUserState:
    """Tests for attaching user to request state."""

    @pytest.mark.asyncio
    async def test_valid_auth_attaches_user_to_state(self):
        """Valid authentication should attach AuthenticatedUser to request.state."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer valid_token"}
        request.state = MagicMock()

        call_next = AsyncMock(return_value=MagicMock())

        mock_token_data = MagicMock()
        mock_token_data.sub = "testuser"

        mock_user = _FakeUser(
            id="user123",
            username="testuser",
            role_id="role456",
            plant_id=None,
            is_active=True,
        )

        mock_role = _FakeRole(
            id="role456",
            name="admin",
            permissions=["*"],
        )

        with patch(
            "mindtrace.apps.inspectra.core.security.decode_token"
        ) as mock_decode, patch(
            "mindtrace.apps.inspectra.repositories.user_repository.UserRepository"
        ) as mock_user_repo_class, patch(
            "mindtrace.apps.inspectra.repositories.role_repository.RoleRepository"
        ) as mock_role_repo_class, patch(
            "mindtrace.apps.inspectra.core.security.AuthenticatedUser"
        ) as mock_auth_user_class:
            mock_decode.return_value = mock_token_data

            mock_user_repo = AsyncMock()
            mock_user_repo.get_by_username.return_value = mock_user
            mock_user_repo_class.return_value = mock_user_repo

            mock_role_repo = AsyncMock()
            mock_role_repo.get_by_id.return_value = mock_role
            mock_role_repo_class.return_value = mock_role_repo

            mock_auth_user = MagicMock()
            mock_auth_user_class.return_value = mock_auth_user

            await middleware.dispatch(request, call_next)

            mock_auth_user_class.assert_called_once_with(
                user_id="user123",
                username="testuser",
                role_id="role456",
                role_name="admin",
                plant_id=None,
                permissions=["*"],
                is_active=True,
            )

            assert request.state.user == mock_auth_user
            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_user_with_plant_id_attached(self):
        """User with plant_id should have it attached to AuthenticatedUser."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = "/admin/users"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer valid_token"}
        request.state = MagicMock()

        call_next = AsyncMock(return_value=MagicMock())

        mock_token_data = MagicMock()
        mock_token_data.sub = "plant_user"

        mock_user = _FakeUser(
            id="user789",
            username="plant_user",
            role_id="role456",
            plant_id="plant_abc",
            is_active=True,
        )

        mock_role = _FakeRole(
            id="role456",
            name="operator",
            permissions=["read"],
        )

        with patch(
            "mindtrace.apps.inspectra.core.security.decode_token"
        ) as mock_decode, patch(
            "mindtrace.apps.inspectra.repositories.user_repository.UserRepository"
        ) as mock_user_repo_class, patch(
            "mindtrace.apps.inspectra.repositories.role_repository.RoleRepository"
        ) as mock_role_repo_class, patch(
            "mindtrace.apps.inspectra.core.security.AuthenticatedUser"
        ) as mock_auth_user_class:
            mock_decode.return_value = mock_token_data

            mock_user_repo = AsyncMock()
            mock_user_repo.get_by_username.return_value = mock_user
            mock_user_repo_class.return_value = mock_user_repo

            mock_role_repo = AsyncMock()
            mock_role_repo.get_by_id.return_value = mock_role
            mock_role_repo_class.return_value = mock_role_repo

            mock_auth_user = MagicMock()
            mock_auth_user_class.return_value = mock_auth_user

            await middleware.dispatch(request, call_next)

            mock_auth_user_class.assert_called_once_with(
                user_id="user789",
                username="plant_user",
                role_id="role456",
                role_name="operator",
                plant_id="plant_abc",
                permissions=["read"],
                is_active=True,
            )


class TestAuthMiddlewareExemptPathsCompleteness:
    """Tests to verify all exempt paths are handled."""

    @pytest.mark.parametrize(
        "path",
        [
            "/auth/login",
            "/auth/register",
            "/license/activate",
            "/license/machine-id",
            "/license/status",
            "/license/validate",
            "/password/validate",
            "/status",
            "/heartbeat",
            "/endpoints",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
    )
    @pytest.mark.asyncio
    async def test_exempt_path(self, path):
        """All exempt paths should bypass authentication."""
        middleware = AuthMiddleware(app=MagicMock())

        request = MagicMock()
        request.url.path = path
        request.method = "GET"

        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
