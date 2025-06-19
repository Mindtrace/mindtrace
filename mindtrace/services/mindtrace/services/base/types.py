from dataclasses import dataclass
from enum import Enum
import json
from uuid import UUID

from pydantic import BaseModel


class ServerStatus(Enum):
    Down = "Down"
    Launching = "Launching"
    FailedToLaunch = "FailedToLaunch"
    Available = "Available"
    Stopping = "Stopping"


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

    status: ServerStatus = ServerStatus.Down
    server_id: UUID | None = None
    message: str | None = None
    details: any = None

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


class SetServerIDInput(BaseModel):
    server_id: UUID