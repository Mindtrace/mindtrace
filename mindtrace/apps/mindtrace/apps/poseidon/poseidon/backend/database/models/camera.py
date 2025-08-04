from mindtrace.database import MindtraceDocument
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, UTC
from pydantic import Field
from beanie import Link, before_event, Insert, Replace, SaveChanges
from .enums import CameraStatus

if TYPE_CHECKING:
    from .organization import Organization
    from .project import Project
    from .user import User

class Camera(MindtraceDocument):
    name: str  # Must be unique per project
    backend: str
    device_name: str

    status: CameraStatus = CameraStatus.INACTIVE
    configuration: Dict[str, Any] = Field(default_factory=dict)

    organization: Link["Organization"]
    project: Link["Project"]
    created_by: Link["User"]

    description: Optional[str] = None
    location: Optional[str] = None
    model_info: Optional[str] = None

    serial_number: Optional[str] = None  # Must be unique per project
    last_ping: Optional[datetime] = None

    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event(Insert)
    def set_created_timestamps(self):
        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now

    @before_event([Replace, SaveChanges])
    def update_timestamp(self):
        self.updated_at = datetime.now(UTC)

    def update_status(self, status: CameraStatus):
        if status in CameraStatus:
            self.status = status

    def update_configuration(self, config: Dict[str, Any]):
        self.configuration.update(config)

    def is_online(self) -> bool:
        return self.status == CameraStatus.ACTIVE

    def get_full_name(self) -> str:
        return f"{self.device_name} ({self.backend})"

    def update_ping(self):
        self.last_ping = datetime.now(UTC)