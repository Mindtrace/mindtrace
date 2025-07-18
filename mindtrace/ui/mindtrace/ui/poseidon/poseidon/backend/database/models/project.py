from mindtrace.database import MindtraceDocument
from typing import Dict, List, Optional, TYPE_CHECKING
from datetime import datetime, UTC
from beanie import Link, before_event, Insert, Replace, SaveChanges
from pydantic import Field
from .enums import ProjectStatus, ProjectType

if TYPE_CHECKING:
    from .organization import Organization
    from .user import User

class Project(MindtraceDocument):
    name: str
    description: Optional[str] = ""

    # Links
    organization: Link["Organization"]
    owner: Optional[Link["User"]] = None

    # Project details
    status: ProjectStatus = ProjectStatus.ACTIVE
    project_type: Optional[ProjectType] = None

    # Settings and metadata
    settings: Dict = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Optional: Project time window
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @before_event(Insert)
    def set_creation_timestamps(self):
        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now

    @before_event([Replace, SaveChanges])
    def update_timestamp(self):
        self.updated_at = datetime.now(UTC)

    def is_active(self) -> bool:
        return self.status == ProjectStatus.ACTIVE

    def add_tag(self, tag: str):
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str):
        if tag in self.tags:
            self.tags.remove(tag)

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def update_setting(self, key: str, value):
        self.settings[key] = value

    def set_status(self, status: ProjectStatus):
        if status not in ProjectStatus:
            raise ValueError(f"Invalid status. Must be one of: {[s.value for s in ProjectStatus]}")
        self.status = status