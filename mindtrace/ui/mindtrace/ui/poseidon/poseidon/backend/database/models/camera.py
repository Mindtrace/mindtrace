from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import List, Optional, Dict, Any
from datetime import datetime

class Camera(MindtraceDocument):
    name: str  # Backend:device_name format
    backend: str
    device_name: str
    status: str  # "active", "inactive", "error"
    configuration: Dict[str, Any] = {}  # exposure, gain, etc.
    organization_id: str
    project_id: str
    created_by: str
    
    # Additional fields for better camera management
    description: Optional[str] = ""
    location: Optional[str] = ""
    model_info: Optional[str] = ""
    serial_number: Optional[str] = ""
    last_ping: Optional[str] = ""
    
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
        """Update camera status and timestamp"""
        valid_statuses = ["active", "inactive", "error"]
        if status in valid_statuses:
            self.status = status
            self.update_timestamp()
    
    def update_configuration(self, config: Dict[str, Any]):
        """Update camera configuration"""
        self.configuration.update(config)
        self.update_timestamp()
    
    def is_online(self) -> bool:
        """Check if camera is online (active status)"""
        return self.status == "active"
    
    def get_full_name(self) -> str:
        """Get descriptive name for the camera"""
        return f"{self.device_name} ({self.backend})"
    
    def update_ping(self):
        """Update last ping timestamp"""
        self.last_ping = datetime.now().isoformat()
        self.update_timestamp()