# tests/unit/mindtrace/apps/inspectra/test_role_service.py

from dataclasses import dataclass
from typing import List

import pytest

from mindtrace.apps.inspectra.app.services.role_service import RoleService
from mindtrace.apps.inspectra.app.schemas.role import RoleCreate, RoleResponse
from mindtrace.apps.inspectra.app.models.role import Role


@dataclass
class _FakeRole(Role):
    """Concrete Role dataclass for fake repo."""
    pass


class FakeRoleRepository:
    """In-memory fake role repository."""

    def __init__(self) -> None:
        self._roles: List[_FakeRole] = []

    async def list(self) -> List[_FakeRole]:
        return list(self._roles)

    async def create(self, payload: RoleCreate) -> _FakeRole:
        role = _FakeRole(
            id=str(len(self._roles) + 1),
            name=payload.name,
            description=payload.description,
        )
        self._roles.append(role)
        return role


class TestRoleService:
    """Unit tests for RoleService."""

    @pytest.fixture
    def service(self) -> RoleService:
        """Create RoleService with fake repository."""
        return RoleService(repo=FakeRoleRepository())

    @pytest.mark.asyncio
    async def test_create_role(self, service: RoleService):
        """create_role should persist a role and return RoleResponse."""
        payload = RoleCreate(name="operator", description="Line operator")
        result: RoleResponse = await service.create_role(payload)

        assert result.id
        assert result.name == "operator"
        assert result.description == "Line operator"

    @pytest.mark.asyncio
    async def test_list_roles(self, service: RoleService):
        """list_roles should return all roles from the repository."""
        await service.create_role(RoleCreate(name="user", description="Default"))
        await service.create_role(RoleCreate(name="admin", description="Administrator"))

        roles = await service.list_roles()

        names = {r.name for r in roles}
        assert names == {"user", "admin"}
        assert all(isinstance(r, RoleResponse) for r in roles)
