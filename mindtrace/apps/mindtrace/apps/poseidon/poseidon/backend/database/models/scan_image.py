from mindtrace.database import MindtraceDocument
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime, UTC
from beanie import Link, before_event, Insert, Replace, SaveChanges
from pydantic import Field
from .enums import ScanImageStatus
from pymongo import IndexModel, ASCENDING, DESCENDING

if TYPE_CHECKING:
    from .organization import Organization
    from .project import Project
    from .camera import Camera
    from .scan import Scan
    from .user import User
    from .scan_classification import ScanClassification

class ScanImage(MindtraceDocument):
    # Required relationships
    organization: Link["Organization"]
    project: Link["Project"]
    camera: Link["Camera"]
    scan: Link["Scan"]

    # Optional relationship
    user: Optional[Link["User"]] = None

    # Status
    status: ScanImageStatus = ScanImageStatus.UPLOADED

    # File information
    file_name: str
    path: str
    bucket_name: Optional[str] = None
    full_path: str

    # Related classifications
    classifications: List[Link["ScanClassification"]] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "ScanImage"
        indexes = [
            IndexModel([("scan.$id", ASCENDING), ("created_at", DESCENDING)], name="scanimg_scan_created"),
            IndexModel([("project.$id", ASCENDING), ("created_at", DESCENDING)], name="scanimg_project_created"),
            IndexModel([("full_path", ASCENDING)], name="scanimg_full_path"),
        ]

    @before_event(Insert)
    def set_creation_timestamps(self):
        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now

    @before_event([Replace, SaveChanges])
    def update_timestamp(self):
        self.updated_at = datetime.now(UTC)

    def add_classification(self, classification: "ScanClassification"):
        """Add a classification to this image"""
        if classification not in self.classifications:
            self.classifications.append(classification)

    def remove_classification(self, classification: "ScanClassification"):
        """Remove a classification from this image"""
        self.classifications = [cls for cls in self.classifications if cls.id != classification.id]

    def is_processed(self) -> bool:
        """Check if image is processed"""
        return self.status == ScanImageStatus.PROCESSED

    def is_failed(self) -> bool:
        """Check if image processing failed"""
        return self.status == ScanImageStatus.FAILED

    def get_file_url(self) -> str:
        """Get the full file URL/path"""
        if self.bucket_name:
            return f"gs://{self.bucket_name}/{self.path}/{self.file_name}"
        return self.full_path
