from mindtrace.database import MindtraceDocument
from typing import Dict, Optional, List, TYPE_CHECKING
from datetime import datetime, UTC
from pydantic import Field
from beanie import Link, before_event, Insert, Replace, SaveChanges

if TYPE_CHECKING:
    from .user import User
    from .project import Project
    from .organization import Organization

class Image(MindtraceDocument):
    filename: str
    gcp_path: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    
    # Link relationships
    uploaded_by: Optional[Link["User"]] = None
    project: Optional[Link["Project"]] = None
    organization: Optional[Link["Organization"]] = None
    
    # Proper datetime fields
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