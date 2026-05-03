from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Scope(str, Enum):
    """Authorization scopes for the distributed agent system."""

    TASKS_SUBMIT = "tasks:submit"
    TASKS_READ = "tasks:read"
    TASKS_CANCEL = "tasks:cancel"
    AGENTS_LIST = "agents:list"
    AGENTS_MANAGE = "agents:manage"
    DLQ_MANAGE = "dlq:manage"
    ALLOWLIST_MANAGE = "allowlist:manage"
    SPANS_INGEST = "spans:ingest"
    METRICS_READ = "metrics:read"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    PROJECT_MEMBER = "project:member"
    PROJECT_ADMIN = "project:admin"
    ORG_MEMBER = "org:member"
    ORG_ADMIN = "org:admin"


class AuthenticatedPrincipal(BaseModel):
    """Verified identity attached to every authenticated request."""

    principal_id: str
    principal_type: Literal["user", "service", "worker", "admin"]
    role: str
    scopes: list[str]
    token_expires_at: datetime | None = None

    def has_scope(self, scope: str | Scope) -> bool:
        scope_value = scope.value if isinstance(scope, Scope) else scope
        return scope_value in self.scopes or "admin" in self.role


class AuthenticationError(Exception):
    """Token missing, expired, or has an invalid signature."""


class AuthorizationError(Exception):
    """Token valid but principal lacks the required scope."""


def require_scope(principal: AuthenticatedPrincipal, scope: str | Scope) -> None:
    """Raise AuthorizationError if the principal lacks the required scope."""
    scope_value = scope.value if isinstance(scope, Scope) else scope
    if not principal.has_scope(scope_value):
        raise AuthorizationError(
            f"Scope {scope_value!r} required but principal {principal.principal_id!r} "
            f"has scopes: {principal.scopes}"
        )


__all__ = [
    "AuthenticatedPrincipal",
    "AuthenticationError",
    "AuthorizationError",
    "Scope",
    "require_scope",
]
