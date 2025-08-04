from mindtrace.database import MindtraceDocument
from typing import Optional, TYPE_CHECKING
from datetime import datetime, UTC
from beanie import Link, before_event, Insert, Replace, SaveChanges
from pydantic import Field

if TYPE_CHECKING:
    from .scan_image import ScanImage
    from .scan import Scan

class ScanClassification(MindtraceDocument):
    # Required relationships
    image: Link["ScanImage"]
    scan: Link["Scan"]
    
    # Classification information
    name: str  # classification name/label
    cls_confidence: Optional[float] = None
    cls_pred_time: Optional[float] = None  # in seconds
    
    # Detection bounding box coordinates
    det_cls: Optional[str] = None  # detected class
    det_x: Optional[float] = None  # x coordinate
    det_y: Optional[float] = None  # y coordinate  
    det_w: Optional[float] = None  # width
    det_h: Optional[float] = None  # height
    
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

    def has_detection_box(self) -> bool:
        """Check if this classification has detection bounding box coordinates"""
        return all([
            self.det_x is not None,
            self.det_y is not None,
            self.det_w is not None,
            self.det_h is not None
        ])

    def get_bounding_box(self) -> Optional[dict]:
        """Get bounding box as a dictionary, if available"""
        if self.has_detection_box():
            return {
                'x': self.det_x,
                'y': self.det_y,
                'width': self.det_w,
                'height': self.det_h,
                'class': self.det_cls
            }
        return None

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if classification confidence is above threshold"""
        return self.cls_confidence is not None and self.cls_confidence >= threshold 