"""Mindtrace Services Module.

This module provides the core services framework for building microservices with
authentication, connection management, and service lifecycle support.
"""

from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.service import Service
from mindtrace.services.core.types import (
    EndpointsSchema,
    Heartbeat,
    HeartbeatSchema,
    PIDFileSchema,
    Scope,
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
    "Scope",
    "ServerIDSchema",
    "Service",
    "ServerStatus",
    "ShutdownSchema",
    "StatusSchema",
]
