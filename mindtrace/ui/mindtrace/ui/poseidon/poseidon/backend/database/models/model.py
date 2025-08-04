from mindtrace.database import MindtraceDocument
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, UTC
from beanie import Link, before_event, Insert, Replace, SaveChanges
from pydantic import Field
from .enums import ModelValidationStatus

if TYPE_CHECKING:
    from .organization import Organization
    from .user import User
    from .project import Project

class Model(MindtraceDocument):
    name: str
    description: str
    version: str

    # Required links
    organization: Link["Organization"]
    created_by: Link["User"]
    project: Link["Project"]

    # Metadata
    type: Optional[str] = None
    framework: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None

    # File paths
    model_path: Optional[str] = None
    config_path: Optional[str] = None
    weights_path: Optional[str] = None

    # Validation and deployment
    validation_status: ModelValidationStatus = ModelValidationStatus.PENDING
    deployment_ready: bool = False

    # Optional performance metrics
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None

    # Metadata and tags
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    is_active: bool = True
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

    def update_validation_status(self, status: ModelValidationStatus):
        if status not in ModelValidationStatus:
            raise ValueError(f"Invalid status. Must be one of: {[s.value for s in ModelValidationStatus]}")
        self.validation_status = status
        self.deployment_ready = status == ModelValidationStatus.VALIDATED

    def update_metrics(
        self,
        accuracy: Optional[float] = None,
        precision: Optional[float] = None,
        recall: Optional[float] = None,
        f1_score: Optional[float] = None
    ):
        if accuracy is not None:
            self.accuracy = accuracy
        if precision is not None:
            self.precision = precision
        if recall is not None:
            self.recall = recall
        if f1_score is not None:
            self.f1_score = f1_score

    def add_tag(self, tag: str):
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str):
        if tag in self.tags:
            self.tags.remove(tag)

    def update_metadata(self, metadata: Dict[str, Any]):
        self.metadata.update(metadata)

    def is_deployment_ready(self) -> bool:
        return self.deployment_ready and self.validation_status == ModelValidationStatus.VALIDATED

    def get_full_name(self) -> str:
        return f"{self.name} v{self.version}"