"""
Routes module for Camera API.

This module contains all FastAPI route definitions organized by functionality.
"""

# Import all routers
from mindtrace.hardware.api.routes.backends import router as backends_router
from mindtrace.hardware.api.routes.cameras import router as cameras_router
from mindtrace.hardware.api.routes.capture import router as capture_router
from mindtrace.hardware.api.routes.config_async import router as config_async_router
from mindtrace.hardware.api.routes.config_persistence import router as config_persistence_router
from mindtrace.hardware.api.routes.config_sync import router as config_sync_router
from mindtrace.hardware.api.routes.network import router as network_router

# Create module-level router objects for easy import
backends = type("Module", (), {"router": backends_router})()
cameras = type("Module", (), {"router": cameras_router})()
capture = type("Module", (), {"router": capture_router})()
config_async = type("Module", (), {"router": config_async_router})()
config_sync = type("Module", (), {"router": config_sync_router})()
config_persistence = type("Module", (), {"router": config_persistence_router})()
network = type("Module", (), {"router": network_router})()

__all__ = [
    "backends",
    "cameras",
    "capture",
    "config_async",
    "config_sync",
    "config_persistence",
    "network",
    # Also export the original router names for backwards compatibility
    "backends_router",
    "cameras_router",
    "capture_router",
    "config_async_router",
    "config_sync_router",
    "config_persistence_router",
    "network_router",
]
