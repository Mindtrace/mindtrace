from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi import HTTPException

from mindtrace.apps.inspectra.services.auth_service import AuthService
from mindtrace.apps.inspectra.schemas.auth import RegisterPayload, LoginPayload, TokenResponse
from mindtrace.apps.inspectra.models.user import User
from mindtrace.apps.inspectra.models.role import Role


@dataclass
class _FakeUser(User):
    """Concrete User dataclass for fake repo (if User is not imported as dataclass)."""
    pass


class FakeUserRepository:
    """In-memory fake user repository for unit testing."""

    def __init__(self) -> None:
        self._users: dict[str, _FakeUser] = {}

    async def get_by_username(self, username: str) -> Optional[_FakeUser]:
        return self._users.get(username)

    async def create_user(self, username: str, password_hash: str, role_id: str) -> _FakeUser:
        user = _FakeUser(
            id=str(len(self._users) + 1),
            username=username,
            password_hash=password_hash,
            role_id=role_id,
            is_active=True,
        )
        self._users[username] = user
        return user


class FakeRoleRepository:
    """In-memory fake role repository for unit testing."""

    def __init__(self) -> None:
        # Pre-seed with default "user" role
        self._roles_by_name: dict[str, Role] = {
            "user": Role(id="role_user", name="user", description="Default user role"),
        }

    async def get_by_name(self, name: str) -> Optional[Role]:
        return self._roles_by_name.get(name)

    async def create(self, payload) -> Role:
        role = Role(
            id=f"role_{len(self._roles_by_name) + 1}",
            name=payload.name,
            description=payload.description,
        )
        self._roles_by_name[payload.name] = role
        return role


class TestAuthService:
    """Unit tests for AuthService (no real DB, using fake repositories)."""

    @pytest.fixture
    def service(self) -> AuthService:
        """Create an AuthService wired to fake repositories."""
        return AuthService(user_repo=FakeUserRepository(), role_repo=FakeRoleRepository())

    @pytest.mark.asyncio
    async def test_register_creates_user_and_returns_token(self, service: AuthService):
        """Register should create a new user and return a valid TokenResponse."""
        payload = RegisterPayload(username="alice", password="secret123")

        token: TokenResponse = await service.register(payload)

        assert token.access_token
        assert token.token_type == "bearer"

        # Ensure user exists in fake repo
        user = await service.user_repo.get_by_username("alice")
        assert user is not None
        assert user.username == "alice"
        assert user.role_id  # single role id set

    @pytest.mark.asyncio
    async def test_register_existing_username_raises(self, service: AuthService):
        """Registering with an existing username should raise HTTP 400."""
        payload = RegisterPayload(username="bob", password="pass1")
        await service.register(payload)  # first time ok

        with pytest.raises(HTTPException) as exc:
            await service.register(payload)  # duplicate
        assert exc.value.status_code == 400
        assert "Username already exists" in exc.value.detail

    @pytest.mark.asyncio
    async def test_login_success_returns_token(self, service: AuthService):
        """Login with correct credentials should return a bearer token."""
        await service.register(RegisterPayload(username="charlie", password="secret123"))

        token = await service.login(LoginPayload(username="charlie", password="secret123"))

        assert token.access_token
        assert token.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials_raise(self, service: AuthService):
        """Login with invalid credentials should raise HTTP 401."""
        # user not registered
        with pytest.raises(HTTPException) as exc:
            await service.login(LoginPayload(username="nobody", password="wrong"))
        assert exc.value.status_code == 401
