"""Authentication module for Mindtrace services.

Provides stateless OAuth2 Bearer token authentication. Applications manage their own
user databases while using this module for token verification.
"""

import inspect
from typing import Awaitable, Callable, Optional, Union

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mindtrace.services.core.types import Scope


class _TokenVerifierState:
    """Module-level state for token verifier."""

    verifier: Optional[Union[Callable[[str], dict], Callable[[str], Awaitable[dict]]]] = None


_state = _TokenVerifierState()


def set_token_verifier(verifier: Union[Callable[[str], dict], Callable[[str], Awaitable[dict]]]):
    """Set a custom token verification function.

    The verifier function can be either synchronous or asynchronous:
    - Accept a token string as input
    - Return a dict with user information if token is valid (or Awaitable[dict] for async)
    - Raise HTTPException if token is invalid

    Args:
        verifier: A function that verifies tokens and returns user info (sync or async)

    Example:
        # Synchronous verifier
        def verify_token(token: str) -> dict:
            # Verify JWT token, check signature, etc.
            # Return user info like {"user_id": "123", "username": "john"}
            pass

        # Asynchronous verifier
        async def verify_token_async(token: str) -> dict:
            # Async token verification (e.g., checking against database)
            pass

        set_token_verifier(verify_token)  # or verify_token_async
    """
    _state.verifier = verifier


def get_token_verifier() -> Optional[Callable[[str], dict]]:
    """Get the current token verification function."""
    return _state.verifier


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="Bearer",
    description="JWT Bearer token authentication. Format: Bearer <token>",
)


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> dict:
    """Verify OAuth2 Bearer token and return user information.

    This dependency can be used with FastAPI endpoints to require authentication.
    It extracts the Bearer token from the Authorization header and verifies it
    using the configured token verifier.

    Args:
        credentials: HTTPAuthorizationCredentials from FastAPI security

    Returns:
        dict: User information from verified token

    Raises:
        HTTPException: If token is missing or invalid
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    verifier = get_token_verifier()

    if verifier is None:
        return {"token": token, "authenticated": True}

    try:
        # Check if verifier is async
        if inspect.iscoroutinefunction(verifier):
            user_info = await verifier(token)
        else:
            user_info = verifier(token)
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_auth_dependency(scope: Scope):
    """Get authentication dependency based on scope.

    Args:
        scope: The endpoint scope (PUBLIC or AUTHENTICATED)

    Returns:
        Security dependency for AUTHENTICATED scope, None for PUBLIC
    """
    if scope == Scope.AUTHENTICATED:
        return Security(verify_token)
    return None
