import json
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from mindtrace.core import TaskSchema


class ServerStatus(Enum):
    DOWN = "Down"
    LAUNCHING = "Launching"
    FAILED_TO_LAUNCH = "FailedToLaunch"
    AVAILABLE = "Available"
    STOPPING = "Stopping"


@dataclass
class Heartbeat:
    """Heartbeat status of a server.

    Attributes:
        status: The current status of the server.
        server_id: The unique identifier of the server.
        message: Human-readable message describing the status of the server.
        details: Additional details about the server status. Individual server subclasses may define their own specific
            protocol for this field (though always a dict). A GatewayServer, for instance, will return a
            dict[UUID, Heartbeat], containing the Heartbeats of all connected services, keyed by their unique server
            IDs.
    """

    status: ServerStatus = ServerStatus.DOWN
    server_id: UUID | None = None
    message: str | None = None
    details: Any = None

    def __str__(self):
        if isinstance(self.details, dict):
            return (
                f"Server ID: {self.server_id}\n"
                f"Status: {self.status}\n"
                f"Message: {self.message}\n"
                f"Details: {json.dumps(self.details, indent=4)}"
            )
        else:
            return (
                f"Server ID: {self.server_id}\nStatus: {self.status}\nMessage: {self.message}\nDetails: {self.details}"
            )


class EndpointsOutput(BaseModel):
    endpoints: list[str]


EndpointsSchema = TaskSchema(name="endpoints", output_schema=EndpointsOutput)


class StatusOutput(BaseModel):
    status: ServerStatus


StatusSchema = TaskSchema(name="status", output_schema=StatusOutput)


class HeartbeatOutput(BaseModel):
    heartbeat: Heartbeat


HeartbeatSchema = TaskSchema(name="heartbeat", output_schema=HeartbeatOutput)


class ServerIDOutput(BaseModel):
    server_id: UUID


ServerIDSchema = TaskSchema(name="server_id", output_schema=ServerIDOutput)


class PIDFileOutput(BaseModel):
    pid_file: str


PIDFileSchema = TaskSchema(name="pid_file", output_schema=PIDFileOutput)


class ShutdownOutput(BaseModel):
    shutdown: bool


ShutdownSchema = TaskSchema(name="shutdown", output_schema=ShutdownOutput)
