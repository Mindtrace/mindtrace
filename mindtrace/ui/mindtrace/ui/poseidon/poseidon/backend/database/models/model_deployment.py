from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import List, Optional, Dict, Any
from datetime import datetime

class ModelDeployment(MindtraceDocument):
    model_id: str
    camera_ids: List[str]  # List of camera IDs
    deployment_status: str  # "pending", "deployed", "failed"
    model_server_url: str
    organization_id: str
    created_by: str
    
    # Deployment configuration
    deployment_config: Dict[str, Any] = {}
    inference_config: Dict[str, Any] = {}
    
    # Resource management
    resource_limits: Dict[str, Any] = {}
    priority: int = 1  # 1 (low) to 10 (high)
    
    # Health monitoring
    health_status: Optional[str] = "unknown"  # "healthy", "unhealthy", "unknown"
    health_check_url: Optional[str] = ""
    last_health_check: Optional[str] = ""
    
    # Performance metrics
    inference_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    
    def __init__(self, **data):
        if 'created_at' not in data or not data['created_at']:
            data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in data or not data['updated_at']:
            data['updated_at'] = datetime.now().isoformat()
        super().__init__(**data)
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now().isoformat()
    
    def update_status(self, status: str):
        """Update deployment status"""
        valid_statuses = ["pending", "deployed", "failed"]
        if status in valid_statuses:
            self.deployment_status = status
            self.update_timestamp()
    
    def update_health_status(self, status: str):
        """Update health status"""
        valid_statuses = ["healthy", "unhealthy", "unknown"]
        if status in valid_statuses:
            self.health_status = status
            self.last_health_check = datetime.now().isoformat()
            self.update_timestamp()
    
    def add_camera(self, camera_id: str):
        """Add a camera to the deployment"""
        if camera_id not in self.camera_ids:
            self.camera_ids.append(camera_id)
            self.update_timestamp()
    
    def remove_camera(self, camera_id: str):
        """Remove a camera from the deployment"""
        if camera_id in self.camera_ids:
            self.camera_ids.remove(camera_id)
            self.update_timestamp()
    
    def record_inference(self, success: bool = True):
        """Record an inference attempt"""
        self.inference_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.update_timestamp()
    
    def get_success_rate(self) -> float:
        """Calculate success rate"""
        if self.inference_count == 0:
            return 0.0
        return (self.success_count / self.inference_count) * 100
    
    def get_failure_rate(self) -> float:
        """Calculate failure rate"""
        if self.inference_count == 0:
            return 0.0
        return (self.failure_count / self.inference_count) * 100
    
    def is_healthy(self) -> bool:
        """Check if deployment is healthy"""
        return (
            self.deployment_status == "deployed" and
            self.health_status == "healthy" and
            self.is_active
        )
    
    def get_camera_count(self) -> int:
        """Get number of cameras in deployment"""
        return len(self.camera_ids)
    
    def update_config(self, config: Dict[str, Any]):
        """Update deployment configuration"""
        self.deployment_config.update(config)
        self.update_timestamp()
    
    def update_inference_config(self, config: Dict[str, Any]):
        """Update inference configuration"""
        self.inference_config.update(config)
        self.update_timestamp()