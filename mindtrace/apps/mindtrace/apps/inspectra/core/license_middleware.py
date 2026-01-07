"""License validation middleware for Inspectra."""

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from mindtrace.apps.inspectra.models.license import LicenseStatus
from mindtrace.apps.inspectra.repositories.license_repository import LicenseRepository

from .cache import CacheKeys, get_cache

# Cache TTL for license (5 minutes)
LICENSE_CACHE_TTL = 300

# Endpoints that don't require license validation
LICENSE_EXEMPT_PATHS = {
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


def invalidate_license_cache() -> None:
    """Invalidate the license cache. Call after license activation."""
    get_cache().invalidate(CacheKeys.LICENSE_ACTIVE)


class LicenseMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates license before processing requests.

    Checks:
    - License exists
    - License is valid (not expired, correct machine)
    - License is active

    Uses caching to reduce database load.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip exempt paths
        path = request.url.path

        # Check if path starts with any exempt path
        for exempt in LICENSE_EXEMPT_PATHS:
            if path == exempt or path.startswith(exempt + "/"):
                return await call_next(request)

        # Also skip for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check cache first
        cache = get_cache()
        license_info = cache.get(CacheKeys.LICENSE_ACTIVE)

        if license_info is None:
            # Fetch from DB and cache
            license_repo = LicenseRepository()
            license_info = await license_repo.get_active_license()
            if license_info:
                cache.set(CacheKeys.LICENSE_ACTIVE, license_info, LICENSE_CACHE_TTL)

        if not license_info:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active license. Please activate a license.",
            )

        if license_info.status == LicenseStatus.EXPIRED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="License has expired. Please renew your license.",
            )

        if license_info.status == LicenseStatus.HARDWARE_MISMATCH:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="License is not valid for this machine.",
            )

        if license_info.status != LicenseStatus.VALID:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid license: {license_info.status.value}",
            )

        # Add license info to request state for downstream use
        request.state.license = license_info

        return await call_next(request)
