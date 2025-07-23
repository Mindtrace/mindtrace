from mindtrace.database import MindtraceDocument
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime, UTC
from beanie import Link, before_event, Insert, Replace, SaveChanges
from pydantic import Field
from .enums import ScanStatus

if TYPE_CHECKING:
    from .organization import Organization
    from .project import Project
    from .model_deployment import ModelDeployment
    from .user import User
    from .scan_image import ScanImage

class Scan(MindtraceDocument):
    # Required relationships
    organization: Link["Organization"]
    project: Link["Project"]
    model_deployment: Link["ModelDeployment"]
    
    # Optional relationship
    user: Optional[Link["User"]] = None
    
    # Status and results
    status: ScanStatus = ScanStatus.PENDING
    cls_result: Optional[str] = None
    cls_confidence: Optional[float] = None
    cls_pred_time: Optional[float] = None  # in seconds
    
    # Related images - back-reference
    images: List[Link["ScanImage"]] = Field(default_factory=list)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event(Insert)
    def set_creation_timestamps(self):
        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now

    @before_event([Replace, SaveChanges])
    def update_timestamp(self):
        self.updated_at = datetime.now(UTC)

    def add_image(self, image: "ScanImage"):
        """Add an image to this scan"""
        if image not in self.images:
            self.images.append(image)

    def remove_image(self, image: "ScanImage"):
        """Remove an image from this scan"""
        self.images = [img for img in self.images if img.id != image.id]

    def is_completed(self) -> bool:
        """Check if scan is completed"""
        return self.status == ScanStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if scan failed"""
        return self.status == ScanStatus.FAILED 