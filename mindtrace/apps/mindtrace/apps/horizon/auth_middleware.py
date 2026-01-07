"""Authentication middleware for Horizon service.

Provides a sample AuthMiddleware demonstrating Bearer token validation
with configurable bypass paths.
"""

import hashlib
import hmac
from typing import Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware with Bearer token validation.

    This middleware demonstrates a simple token-based authentication scheme.
    It can be enabled/disabled via configuration and supports bypass paths
    for endpoints that should be publicly accessible.

    Example:
        from mindtrace.services import Service

        class MyService(Service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.app.add_middleware(AuthMiddleware, secret_key="...", enabled=True)
    """

    def __init__(
        self,
        app,
        secret_key: str = "dev-secret-key",
        enabled: bool = False,
        bypass_paths: Optional[Set[str]] = None,
    ):
        """Initialize the AuthMiddleware.

        Args:
            app: The ASGI application
            secret_key: Secret key for token validation
            enabled: Whether to enable authentication checks
            bypass_paths: Paths that bypass authentication (e.g., health checks)
        """
        super().__init__(app)
        self.secret_key = secret_key
        self.enabled = enabled
        self.bypass_paths = bypass_paths or {
            "/status",
            "/heartbeat",
            "/endpoints",
            "/server_id",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/",
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request through authentication checks.

        Args:
            request: The incoming request
            call_next: The next middleware/endpoint in the chain

        Returns:
            Response from the next handler or 401/403 error response
        """
        # Skip authentication if disabled
        if not self.enabled:
            return await call_next(request)

        # Check if path should bypass authentication
        path = request.url.path.rstrip("/") or "/"
        if path in self.bypass_paths or self._is_bypass_prefix(path):
            return await call_next(request)

        # Extract and validate token
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
            )

        # Expect "Bearer <token>" format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header format. Expected: Bearer <token>"},
            )

        token = parts[1]
        if not self._validate_token(token):
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or expired token"},
            )

        # Token is valid, proceed with request
        return await call_next(request)

    def _is_bypass_prefix(self, path: str) -> bool:
        """Check if path starts with any bypass prefix.

        This handles cases like /mcp-server/* or /docs/*.
        """
        bypass_prefixes = {"/mcp-server", "/docs"}
        return any(path.startswith(prefix) for prefix in bypass_prefixes)

    def _validate_token(self, token: str) -> bool:
        """Validate the provided token.

        This is a simple HMAC-based validation. In production, you might
        use JWT tokens or integrate with an OAuth provider.

        Args:
            token: The token to validate

        Returns:
            True if the token is valid, False otherwise
        """
        # Simple validation: token should be HMAC-SHA256 of "horizon:<timestamp>"
        # where timestamp is within the last hour
        # For demo purposes, we also accept a static dev token
        if token == "dev-token":
            return True

        try:
            # Expected format: <timestamp>.<signature>
            parts = token.split(".")
            if len(parts) != 2:
                return False

            timestamp_str, signature = parts
            timestamp = int(timestamp_str)

            # Verify signature
            expected_sig = self._generate_signature(timestamp_str)
            return hmac.compare_digest(signature, expected_sig)
        except (ValueError, TypeError):
            return False

    def _generate_signature(self, data: str) -> str:
        """Generate HMAC signature for the given data.

        Args:
            data: The data to sign

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        return hmac.new(
            self.secret_key.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def generate_token(cls, secret_key: str, timestamp: int) -> str:
        """Generate a valid authentication token.

        This is a helper method for clients to generate tokens.

        Args:
            secret_key: The secret key (must match server config)
            timestamp: Unix timestamp for the token

        Returns:
            A valid token string in format "<timestamp>.<signature>"

        Example:
            ```python
            import time
            token = AuthMiddleware.generate_token("my-secret", int(time.time()))
            # Use token in Authorization header: "Bearer <token>"
            ```
        """
        timestamp_str = str(timestamp)
        signature = hmac.new(
            secret_key.encode(),
            timestamp_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{timestamp_str}.{signature}"
