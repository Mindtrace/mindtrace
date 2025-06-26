from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import Dict, List, Optional
from datetime import datetime

class Project(MindtraceDocument):
    name: str
    description: Optional[str] = ""
    organization_id: str  # Required - tenant isolation
    
    # Project details
    status: str = "active"  # active, inactive, completed, archived
    project_type: Optional[str] = None  # inspection, audit, etc.
    
    # Project settings and metadata
    settings: Dict = {}
    tags: List[str] = []
    
    # Ownership
    owner_id: Optional[str] = None  # User who created/owns the project
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    
    # Optional: Project dates
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    def __init__(self, **data):
        if 'created_at' not in data or not data['created_at']:
            data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in data or not data['updated_at']:
            data['updated_at'] = datetime.now().isoformat()
        super().__init__(**data)
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now().isoformat()
    
    def is_active(self) -> bool:
        """Check if project is active"""
        return self.status == "active"
    
    def add_tag(self, tag: str):
        """Add a tag to the project"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.update_timestamp()
    
    def remove_tag(self, tag: str):
        """Remove a tag from the project"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.update_timestamp()
    
    def get_setting(self, key: str, default=None):
        """Get a specific setting value"""
        return self.settings.get(key, default)
    
    def update_setting(self, key: str, value):
        """Update a specific setting"""
        self.settings[key] = value
        self.update_timestamp()
    
    def set_status(self, status: str):
        """Update project status"""
        valid_statuses = ["active", "inactive", "completed", "archived"]
        if status in valid_statuses:
            self.status = status
            self.update_timestamp()
        else:
            raise ValueError(f"Invalid status. Must be one of: {valid_statuses}") 