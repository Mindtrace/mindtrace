"""Shared constants for Inspectra."""

from typing import FrozenSet

# Paths that bypass authentication
AUTH_EXEMPT_PATHS: FrozenSet[str] = frozenset(
    {
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
        "/server_id",
        "/pid_file",
        "/shutdown",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# Paths that bypass license validation
LICENSE_EXEMPT_PATHS: FrozenSet[str] = frozenset(
    {
        "/license/activate",
        "/license/machine-id",
        "/license/status",
        "/license/validate",
        "/auth/login",
        "/auth/register",
        "/status",
        "/heartbeat",
        "/endpoints",
        "/server_id",
        "/pid_file",
        "/shutdown",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# Special characters for password validation
SPECIAL_CHARS: FrozenSet[str] = frozenset(
    set("!@#$%^&*()_+-=[]{}|;':\",./<>?`~")
)

# Default pagination settings
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

# Token settings
DEFAULT_JWT_EXPIRES_IN = 86400  # 24 hours
DEFAULT_JWT_ALGORITHM = "HS256"

# Login tracking settings
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_DURATION_SECONDS = 900  # 15 minutes

# Cache TTL settings
LICENSE_CACHE_TTL = 300  # 5 minutes
PASSWORD_POLICY_CACHE_TTL = 3600  # 1 hour
