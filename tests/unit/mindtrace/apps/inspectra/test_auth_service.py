from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi import HTTPException

from mindtrace.apps.inspectra.inspectra import InspectraService
from mindtrace.apps.inspectra.models import (
    LoginPayload,
    RegisterPayload,
    Role,
    TokenResponse,
)

# ---------------------------------------------------------------------------
# Fake repositories (pure in-memory, no Mongo)
# ---------------------------------------------------------------------------

@dataclass
class _FakeUser:
    id: str
    username: str
    password_hash: str
    role_id: str
    is_active: bool = True


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
        # Pre-seed with default "user" role (mirrors real behaviour)
        self._roles_by_name: dict[str, Role] = {
            "user": Role(id="role_user", name="user", description="Default user role"),
        }

    async def get_by_name(self, name: str) -> Optional[Role]:
        return self._roles_by_name.get(name)

    async def create(self, payload) -> Role:
        role = Role(
            id=f"role_{len(self._roles_by_name) + 1}",
            name=payload.name,
            description=getattr(payload, "description", None),
            permissions=getattr(payload, "permissions", None),
        )
        self._roles_by_name[role.name] = role
        return role


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAuthBehaviour:
    """Unit tests for Inspectra auth logic using fake repositories."""

    @pytest.fixture
    def service(self) -> InspectraService:
        """
        Create an InspectraService wired to fake repositories.

        We don't care about DB wiring here – this is pure unit-level logic.
        """
        svc = InspectraService(enable_db=False)

        # IMPORTANT: InspectraService now uses lazy properties backed by private fields.
        svc._user_repo = FakeUserRepository()
        svc._role_repo = FakeRoleRepository()

        return svc

    @pytest.mark.asyncio
    async def test_register_creates_user_and_returns_token(self, service: InspectraService):
        payload = RegisterPayload(username="alice", password="secret123")

        token = await service.register(payload)

        assert isinstance(token, TokenResponse)
        assert token.access_token

        # token_type may be defaulted or omitted depending on your TokenResponse model
        if hasattr(token, "token_type"):
            assert token.token_type == "bearer"

        user = await service.user_repo.get_by_username("alice")
        assert user is not None
        assert user.username == "alice"
        assert user.role_id  # default role id set

    @pytest.mark.asyncio
    async def test_register_existing_username_raises(self, service: InspectraService):
        payload = RegisterPayload(username="bob", password="pass1")
        await service.register(payload)

        with pytest.raises(HTTPException) as exc:
            await service.register(payload)

        assert exc.value.status_code == 400
        assert "Username already exists" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_login_success_returns_token(self, service: InspectraService):
        await service.register(RegisterPayload(username="charlie", password="secret123"))

        token = await service.login(LoginPayload(username="charlie", password="secret123"))

        assert isinstance(token, TokenResponse)
        assert token.access_token
        if hasattr(token, "token_type"):
            assert token.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials_raise(self, service: InspectraService):
        with pytest.raises(HTTPException) as exc:
            await service.login(LoginPayload(username="nobody", password="wrong"))

        assert exc.value.status_code == 401