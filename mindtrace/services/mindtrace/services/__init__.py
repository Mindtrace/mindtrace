from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.service import Service
from mindtrace.services.core.types import (
    EndpointsSchema,
    Heartbeat,
    HeartbeatSchema,
    PIDFileSchema,
    ServerIDSchema,
    ServerStatus,
    ShutdownSchema,
    StatusSchema,
)
from mindtrace.services.core.utils import generate_connection_manager
from mindtrace.services.gateway.gateway import Gateway
from mindtrace.services.gateway.proxy_connection_manager import ProxyConnectionManager
from mindtrace.services.gateway.types import AppConfig, RegisterAppTaskSchema
from mindtrace.services.samples.echo_service import EchoService

# Activate the global service monitor — registers launch/shutdown hooks on
# the Service class so all subsequent launches are tracked automatically.
# Uses a try/except so monitoring is never a hard dependency of services.
try:
    from mindtrace.services.monitoring.monitor import _register_global_hooks
    _register_global_hooks()
except Exception:  # ImportError or any unexpected error at import time
    pass

__all__ = [
    "AppConfig",
    "ConnectionManager",
    "EchoService",
    "EndpointsSchema",
    "Gateway",
    "generate_connection_manager",
    "Heartbeat",
    "HeartbeatSchema",
    "PIDFileSchema",
    "ProxyConnectionManager",
    "RegisterAppTaskSchema",
    "ServerIDSchema",
    "Service",
    "ServerStatus",
    "ShutdownSchema",
    "StatusSchema",
]
