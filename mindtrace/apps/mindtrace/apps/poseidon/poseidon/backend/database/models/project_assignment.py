from mindtrace.database import MindtraceDocument
from typing import TYPE_CHECKING
from datetime import datetime, UTC
from .enums import ProjectRole
from beanie import Link, before_event, Insert, Replace, SaveChanges
from pydantic import Field

if TYPE_CHECKING:
    from .user import User
    from .project import Project

class ProjectAssignment(MindtraceDocument):
    user: Link["User"]
    project: Link["Project"]
    role: ProjectRole = ProjectRole.VIEWER
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assigned_by: Link["User"] = None  # Who assigned this user
    
    @before_event(Insert)
    async def set_timestamps(self):
        self.assigned_at = datetime.now(UTC)
    
    class Settings:
        name = "project_assignments"
        indexes = [
            [("user", 1), ("project", 1)],  # Unique constraint
        ]