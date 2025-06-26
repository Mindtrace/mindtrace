from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import List, Optional, Dict
from datetime import datetime

class User(MindtraceDocument):
    username: str
    email: str
    password_hash: str
    organization_id: str  # Required - primary tenant
    
    # Organization-level roles
    org_roles: List[str] = ["user"]  # admin, user, super_admin
    
    # Project assignments with roles
    project_assignments: List[Dict] = []  # {project_id: str, roles: List[str]}
    
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
    
    def has_org_role(self, role: str) -> bool:
        """Check if user has a specific organization role"""
        return role in self.org_roles
    
    def has_project_role(self, project_id: str, role: str) -> bool:
        """Check if user has a specific role in a project"""
        for assignment in self.project_assignments:
            if assignment.get("project_id") == project_id:
                return role in assignment.get("roles", [])
        return False
    
    def add_project_assignment(self, project_id: str, roles: List[str]):
        """Add or update project assignment"""
        for assignment in self.project_assignments:
            if assignment.get("project_id") == project_id:
                assignment["roles"] = list(set(assignment.get("roles", []) + roles))
                return
        self.project_assignments.append({"project_id": project_id, "roles": roles})
    
    def remove_project_assignment(self, project_id: str):
        """Remove project assignment"""
        self.project_assignments = [
            assignment for assignment in self.project_assignments 
            if assignment.get("project_id") != project_id
        ]
    
    def get_user_project_roles(self, project_id: str) -> List[str]:
        """Get user's roles for a specific project"""
        for assignment in self.project_assignments:
            if assignment.get("project_id") == project_id:
                return assignment.get("roles", [])
        return [] 