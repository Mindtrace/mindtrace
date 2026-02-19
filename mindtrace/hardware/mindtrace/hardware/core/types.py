"""
Core types and enums for hardware services.

This module provides shared type definitions used across hardware services.
"""

from enum import Enum


class ServiceStatus(str, Enum):
    """Health check status for hardware services.

    Usage:
        from mindtrace.hardware.core.types import ServiceStatus

        response = service.health_check()
        if response.status != ServiceStatus.HEALTHY:
            handle_unhealthy_service()
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
