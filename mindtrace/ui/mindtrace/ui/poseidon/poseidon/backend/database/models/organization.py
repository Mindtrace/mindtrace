from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import Dict, Optional
from datetime import datetime
import secrets

class Organization(MindtraceDocument):
    name: str
    description: Optional[str] = ""
    settings: Dict = {}
    
    # Admin registration key for this organization
    admin_registration_key: str = ""
    
    # Subscription/plan info
    subscription_plan: str = "basic"  # basic, pro, enterprise
    max_users: Optional[int] = None
    max_projects: Optional[int] = None
    
    # Status
    is_active: bool = True
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    
    def __init__(self, **data):
        if 'created_at' not in data or not data['created_at']:
            data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in data or not data['updated_at']:
            data['updated_at'] = datetime.now().isoformat()
        if 'admin_registration_key' not in data or not data['admin_registration_key']:
            data['admin_registration_key'] = self.generate_admin_key()
        super().__init__(**data)
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now().isoformat()
    
    def get_setting(self, key: str, default=None):
        """Get a specific setting value"""
        return self.settings.get(key, default)
    
    def update_setting(self, key: str, value):
        """Update a specific setting"""
        self.settings[key] = value
        self.update_timestamp()
    
    def is_within_limits(self, user_count: int = 0, project_count: int = 0) -> bool:
        """Check if organization is within subscription limits"""
        if self.max_users and user_count >= self.max_users:
            return False
        if self.max_projects and project_count >= self.max_projects:
            return False
        return True
    
    def generate_admin_key(self) -> str:
        """Generate a secure admin registration key"""
        return f"ORG_{secrets.token_urlsafe(32)}"
    
    def regenerate_admin_key(self):
        """Regenerate the admin registration key"""
        self.admin_registration_key = self.generate_admin_key()
        self.update_timestamp() 