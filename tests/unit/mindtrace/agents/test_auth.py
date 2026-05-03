"""Unit tests for the agents auth module."""
from __future__ import annotations

import pytest
from mindtrace.agents.auth.principals import (
    AuthenticatedPrincipal,
    AuthenticationError,
    AuthorizationError,
    Scope,
    require_scope,
)
from mindtrace.agents.auth.validators import HMACAPIKeyValidator, WorkerTokenValidator
from mindtrace.agents.auth.dev import DevJWKSSigner


def _admin_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="admin-1",
        principal_type="admin",
        role="admin",
        scopes=[s.value for s in Scope],
    )


def _user_principal(scopes: list[str] | None = None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="user-1",
        principal_type="user",
        role="user",
        scopes=scopes or [Scope.TASKS_SUBMIT.value, Scope.TASKS_READ.value],
    )


class TestAuthenticatedPrincipal:
    def test_has_scope_present(self):
        p = _user_principal()
        assert p.has_scope(Scope.TASKS_SUBMIT)

    def test_has_scope_missing(self):
        p = _user_principal()
        assert not p.has_scope(Scope.AGENTS_MANAGE)

    def test_admin_role_grants_all(self):
        p = _admin_principal()
        assert p.has_scope("anything")


class TestRequireScope:
    def test_passes_for_present_scope(self):
        p = _user_principal([Scope.TASKS_SUBMIT.value])
        require_scope(p, Scope.TASKS_SUBMIT)  # should not raise

    def test_raises_for_missing_scope(self):
        p = _user_principal([Scope.TASKS_READ.value])
        with pytest.raises(AuthorizationError):
            require_scope(p, Scope.AGENTS_MANAGE)

    def test_accepts_string_scope(self):
        p = _user_principal(["tasks:submit"])
        require_scope(p, "tasks:submit")

    def test_new_memory_scopes_exist(self):
        assert Scope.MEMORY_READ.value == "memory:read"
        assert Scope.MEMORY_WRITE.value == "memory:write"
        assert Scope.PROJECT_MEMBER.value == "project:member"
        assert Scope.PROJECT_ADMIN.value == "project:admin"
        assert Scope.ORG_MEMBER.value == "org:member"
        assert Scope.ORG_ADMIN.value == "org:admin"


class TestHMACAPIKeyValidator:
    async def test_valid_key(self):
        validator = HMACAPIKeyValidator()
        validator.register_key(
            "my-secret-key",
            principal_id="svc-1",
            role="service",
            scopes=["tasks:submit"],
        )
        principal = await validator.validate("my-secret-key")
        assert principal.principal_id == "svc-1"
        assert principal.role == "service"

    async def test_invalid_key_raises(self):
        validator = HMACAPIKeyValidator()
        with pytest.raises(AuthenticationError):
            await validator.validate("wrong-key")


class TestWorkerTokenValidator:
    async def test_valid_token(self):
        validator = WorkerTokenValidator(secret="test-secret-123")
        principal = await validator.validate("test-secret-123")
        assert principal.principal_type == "worker"
        assert "spans:ingest" in principal.scopes

    async def test_invalid_token_raises(self):
        validator = WorkerTokenValidator(secret="correct-secret")
        with pytest.raises(AuthenticationError):
            await validator.validate("wrong-secret")

    async def test_empty_secret_raises(self):
        validator = WorkerTokenValidator(secret="")
        with pytest.raises(AuthenticationError):
            await validator.validate("anything")


class TestDevJWKSSigner:
    def test_make_principal(self):
        signer = DevJWKSSigner()
        p = signer.make_principal(principal_id="dev-user", role="user")
        assert p.principal_id == "dev-user"
        assert p.role == "user"
        assert len(p.scopes) > 0

    def test_make_principal_custom_scopes(self):
        signer = DevJWKSSigner()
        p = signer.make_principal(scopes=["tasks:submit", "agents:list"])
        assert "tasks:submit" in p.scopes
        assert "agents:list" in p.scopes
