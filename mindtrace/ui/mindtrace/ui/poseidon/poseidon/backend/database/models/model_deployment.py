from mindtrace.database import MindtraceDocument
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, UTC
from pydantic import Field
from beanie import Link, before_event, Insert, Replace, SaveChanges
from .enums import DeploymentStatus, HealthStatus

if TYPE_CHECKING:
    from .model import Model
    from .organization import Organization
    from .user import User
    from .project import Project

class ModelDeployment(MindtraceDocument):
    model: Link["Model"]
    organization: Link["Organization"]
    project: Link["Project"]
    created_by: Link["User"]

    camera_ids: List[str] = Field(default_factory=list)
    deployment_status: DeploymentStatus = DeploymentStatus.PENDING
    model_server_url: str

    # Configurations
    deployment_config: Dict[str, Any] = Field(default_factory=dict)
    inference_config: Dict[str, Any] = Field(default_factory=dict)

    # Resources
    resource_limits: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 1  # 1 (low) to 10 (high)

    # Health
    health_status: HealthStatus = HealthStatus.UNKNOWN
    health_check_url: Optional[str] = None
    last_health_check: Optional[datetime] = None

    # Metrics
    inference_count: int = 0
    success_count: int = 0
    failure_count: int = 0

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

    def update_status(self, status: DeploymentStatus):
        if status in DeploymentStatus:
            self.deployment_status = status

    def update_health_status(self, status: HealthStatus):
        if status in HealthStatus:
            self.health_status = status
            self.last_health_check = datetime.now(UTC)

    def add_camera(self, camera_id: str):
        if camera_id not in self.camera_ids:
            self.camera_ids.append(camera_id)

    def remove_camera(self, camera_id: str):
        if camera_id in self.camera_ids:
            self.camera_ids.remove(camera_id)

    def record_inference(self, success: bool = True):
        self.inference_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

    def get_success_rate(self) -> float:
        return (self.success_count / self.inference_count) * 100 if self.inference_count else 0.0

    def get_failure_rate(self) -> float:
        return (self.failure_count / self.inference_count) * 100 if self.inference_count else 0.0

    def is_healthy(self) -> bool:
        return (
            self.deployment_status == DeploymentStatus.DEPLOYED and
            self.health_status == HealthStatus.HEALTHY and
            self.is_active
        )

    def get_camera_count(self) -> int:
        return len(self.camera_ids)

    def update_config(self, config: Dict[str, Any]):
        self.deployment_config.update(config)

    def update_inference_config(self, config: Dict[str, Any]):
        self.inference_config.update(config)
