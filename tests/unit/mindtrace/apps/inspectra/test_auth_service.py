from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi import HTTPException

from mindtrace.apps.inspectra.inspectra import InspectraService
from mindtrace.apps.inspectra.models import (
    LoginPayload,
    RegisterPayload,
    TokenResponse,
)

# ---------------------------------------------------------------------------
# Fake repositories (pure in-memory, no Mongo)
# ---------------------------------------------------------------------------

@dataclass
class _FakeUser:
    """
    Lightweight in-memory User model used by FakeUserRepository.

    Mirrors the shape required by InspectraService auth logic
    without any persistence or database dependency.
    """
    id: str
    username: str
    password_hash: str
    role_id: str
    plant_id: Optional[str] = None
    is_active: bool = True


@dataclass
class _FakeRole:
    """
    Lightweight in-memory Role model used by FakeRoleRepository.

    Mirrors the shape required by InspectraService auth logic
    without any persistence or database dependency.
    """
    id: str
    name: str
    description: Optional[str] = None
    permissions: Optional[list] = None


class FakeUserRepository:
    """
    In-memory fake user repository for unit testing auth behaviour.

    Simulates:
    - user lookup by username
    - user creation
    """

    def __init__(self) -> None:
        self._users: dict[str, _FakeUser] = {}

    async def get_by_username(self, username: str) -> Optional[_FakeUser]:
        """Return a user by username if it exists."""
        return self._users.get(username)

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role_id: str,
        plant_id: Optional[str] = None,
    ) -> _FakeUser:
        """Create and store a new fake user."""
        user = _FakeUser(
            id=str(len(self._users) + 1),
            username=username,
            password_hash=password_hash,
            role_id=role_id,
            plant_id=plant_id,
            is_active=True,
        )
        self._users[username] = user
        return user


class FakeRoleRepository:
    """
    In-memory fake role repository for unit testing.

    Pre-seeded with a default 'user' role to mirror
    Inspectra's real startup behaviour.
    """

    def __init__(self) -> None:
        self._roles_by_name: dict[str, _FakeRole] = {
            "user": _FakeRole(
                id="role_user",
                name="user",
                description="Default user role",
            ),
        }

    async def get_by_name(self, name: str) -> Optional[_FakeRole]:
        """Return a role by name if it exists."""
        return self._roles_by_name.get(name)

    async def create(self, payload) -> _FakeRole:
        """Create and store a new role."""
        role = _FakeRole(
            id=f"role_{len(self._roles_by_name) + 1}",
            name=payload.name,
            description=getattr(payload, "description", None),
            permissions=getattr(payload, "permissions", None),
        )
        self._roles_by_name[role.name] = role
        return role


class FakePasswordPolicyRepository:
    """
    In-memory fake password policy repository for unit testing.

    Returns None for default policy (no password validation).
    """

    async def get_default_policy(self):
        """Return None to skip password policy validation."""
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAuthBehaviour:
    """
    Unit tests for Inspectra authentication logic.

    These tests validate:
    - user registration behaviour
    - duplicate username handling
    - login success and failure cases

    All tests run with in-memory fake repositories (no DB).
    """

    @pytest.fixture
    def service(self) -> InspectraService:
        """
        Create an InspectraService instance wired to fake repositories.

        This isolates auth logic from:
        - MongoDB
        - networking
        - middleware
        """
        svc = InspectraService(enable_db=False)

        svc._user_repo = FakeUserRepository()
        svc._role_repo = FakeRoleRepository()
        svc._password_policy_repo = FakePasswordPolicyRepository()

        return svc

    @pytest.mark.asyncio
    async def test_register_creates_user_and_returns_token(self, service: InspectraService):
        """
        Registering a new user should:
        - persist the user
        - assign a default role
        - return a bearer access token
        """
        payload = RegisterPayload(username="alice", password="secret123")

        token = await service.register(payload)

        assert isinstance(token, TokenResponse)
        assert token.access_token

        if hasattr(token, "token_type"):
            assert token.token_type == "bearer"

        user = await service.user_repo.get_by_username("alice")
        assert user is not None
        assert user.username == "alice"
        assert user.role_id

    @pytest.mark.asyncio
    async def test_register_existing_username_raises(self, service: InspectraService):
        """
        Registering with an existing username should fail
        with HTTP 400.
        """
        payload = RegisterPayload(username="bob", password="pass1")
        await service.register(payload)

        with pytest.raises(HTTPException) as exc:
            await service.register(payload)

        assert exc.value.status_code == 400
        assert "Username already exists" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_login_success_returns_token(self, service: InspectraService):
        """
        Logging in with valid credentials should return
        a bearer access token.
        """
        await service.register(RegisterPayload(username="charlie", password="secret123"))

        token = await service.login(
            LoginPayload(username="charlie", password="secret123")
        )

        assert isinstance(token, TokenResponse)
        assert token.access_token

        if hasattr(token, "token_type"):
            assert token.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials_raise(self, service: InspectraService):
        """
        Logging in with invalid credentials should raise
        HTTP 401 Unauthorized.
        """
        with pytest.raises(HTTPException) as exc:
            await service.login(LoginPayload(username="nobody", password="wrong"))

        assert exc.value.status_code == 401
