from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

from .principals import AuthenticatedPrincipal, AuthenticationError


class JWKSValidator:
    """Validates JWTs against a JWKS endpoint.

    Requires: pip install 'pyjwt[crypto]>=2.0' httpx>=0.25
    Configure MINDTRACE_JWKS_URL env var before use.
    """

    def __init__(self, jwks_url: str | None = None, audience: str | None = None) -> None:
        self._jwks_url = jwks_url or os.environ.get("MINDTRACE_JWKS_URL", "")
        self._audience = audience
        self._jwks_cache: dict[str, Any] | None = None
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 300.0

    async def validate(self, token: str) -> AuthenticatedPrincipal:
        """Validate a JWT and return an AuthenticatedPrincipal.

        Raises AuthenticationError on failure.
        """
        try:
            import jwt as pyjwt
        except ImportError as e:
            raise ImportError(
                "JWT validation requires pyjwt[crypto]. "
                "Install it with: pip install 'pyjwt[crypto]>=2.0'"
            ) from e

        try:
            jwks = await self._get_jwks()
            header = pyjwt.get_unverified_header(token)
            kid = header.get("kid")
            key = self._find_key(jwks, kid)
            options: dict[str, Any] = {"verify_exp": True}
            kwargs: dict[str, Any] = {"algorithms": [header.get("alg", "RS256")], "options": options}
            if self._audience:
                kwargs["audience"] = self._audience
            payload = pyjwt.decode(token, key, **kwargs)
        except Exception as exc:
            raise AuthenticationError(f"JWT validation failed: {exc}") from exc

        scopes = payload.get("scopes", payload.get("scope", "").split())
        if isinstance(scopes, str):
            scopes = scopes.split()

        return AuthenticatedPrincipal(
            principal_id=payload.get("sub", ""),
            principal_type="user",
            role=payload.get("role", "user"),
            scopes=scopes,
            token_expires_at=None,
        )

    async def _get_jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._jwks_cache is not None and (now - self._cache_ts) < self._cache_ttl:
            return self._jwks_cache
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "JWKS fetching requires httpx. Install it with: pip install httpx>=0.25"
            ) from e
        async with httpx.AsyncClient() as client:
            resp = await client.get(self._jwks_url, timeout=10.0)
            resp.raise_for_status()
            self._jwks_cache = resp.json()
            self._cache_ts = now
        return self._jwks_cache  # type: ignore[return-value]

    def _find_key(self, jwks: dict[str, Any], kid: str | None) -> Any:
        try:
            from jwt.algorithms import RSAAlgorithm
        except ImportError as e:
            raise ImportError("pyjwt[crypto] required for RSA key parsing") from e

        for key_data in jwks.get("keys", []):
            if kid is None or key_data.get("kid") == kid:
                return RSAAlgorithm.from_jwk(key_data)
        raise AuthenticationError(f"No matching JWK found for kid={kid!r}")


class HMACAPIKeyValidator:
    """Validates HMAC-SHA256 API keys stored as hashes in a backend (e.g. Redis)."""

    def __init__(self, key_store: dict[str, dict] | None = None) -> None:
        self._store: dict[str, dict] = key_store or {}

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def validate(self, raw_key: str) -> AuthenticatedPrincipal:
        """Validate an HMAC API key and return an AuthenticatedPrincipal."""
        key_hash = self._hash_key(raw_key)
        entry = self._store.get(key_hash)
        if entry is None:
            raise AuthenticationError("Unknown or revoked API key")
        return AuthenticatedPrincipal(
            principal_id=entry.get("principal_id", "service"),
            principal_type="service",
            role=entry.get("role", "service"),
            scopes=entry.get("scopes", []),
        )

    def register_key(
        self,
        raw_key: str,
        principal_id: str,
        role: str = "service",
        scopes: list[str] | None = None,
    ) -> str:
        """Register an API key (stores only the hash). Returns the hash."""
        key_hash = self._hash_key(raw_key)
        self._store[key_hash] = {
            "principal_id": principal_id,
            "role": role,
            "scopes": scopes or [],
        }
        return key_hash


class WorkerTokenValidator:
    """Validates the internal worker secret (MINDTRACE_INTERNAL_SECRET env var)."""

    def __init__(self, secret: str | None = None) -> None:
        self._secret = secret or os.environ.get("MINDTRACE_INTERNAL_SECRET", "")

    async def validate(self, token: str) -> AuthenticatedPrincipal:
        """Validate the worker internal secret token."""
        if not self._secret:
            raise AuthenticationError("MINDTRACE_INTERNAL_SECRET is not configured")
        if not hmac.compare_digest(token.encode(), self._secret.encode()):
            raise AuthenticationError("Invalid worker token")
        return AuthenticatedPrincipal(
            principal_id="worker",
            principal_type="worker",
            role="worker",
            scopes=["spans:ingest", "agents:list"],
        )


__all__ = ["HMACAPIKeyValidator", "JWKSValidator", "WorkerTokenValidator"]
