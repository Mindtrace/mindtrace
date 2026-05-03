from __future__ import annotations

import time
from typing import Any

from .principals import AuthenticatedPrincipal, Scope


class DevJWKSSigner:
    """Fast local JWT signer for development and testing.

    Generates self-signed RS256 JWTs without an external IdP.
    NOT for production use.
    """

    def __init__(self) -> None:
        self._private_key: Any = None
        self._public_key: Any = None
        self._kid = "dev-key-1"

    def _ensure_keys(self) -> None:
        if self._private_key is not None:
            return
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
        except ImportError as e:
            raise ImportError(
                "DevJWKSSigner requires cryptography. "
                "Install it with: pip install 'pyjwt[crypto]>=2.0'"
            ) from e
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        self._public_key = self._private_key.public_key()

    def sign_token(
        self,
        principal_id: str = "dev-user",
        role: str = "user",
        scopes: list[str] | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Create a signed JWT for local development."""
        self._ensure_keys()
        try:
            import jwt as pyjwt
        except ImportError as e:
            raise ImportError("DevJWKSSigner requires pyjwt[crypto]") from e

        now = int(time.time())
        payload = {
            "sub": principal_id,
            "iat": now,
            "exp": now + ttl_seconds,
            "role": role,
            "scopes": scopes or [Scope.TASKS_SUBMIT.value, Scope.TASKS_READ.value],
        }
        return pyjwt.encode(
            payload,
            self._private_key,
            algorithm="RS256",
            headers={"kid": self._kid},
        )

    def make_principal(
        self,
        principal_id: str = "dev-user",
        role: str = "user",
        scopes: list[str] | None = None,
    ) -> AuthenticatedPrincipal:
        """Create a principal directly without JWT overhead (for tests)."""
        return AuthenticatedPrincipal(
            principal_id=principal_id,
            principal_type="user",
            role=role,
            scopes=scopes or [Scope.TASKS_SUBMIT.value, Scope.TASKS_READ.value],
        )


__all__ = ["DevJWKSSigner"]
