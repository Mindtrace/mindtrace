import reflex as rx
from typing import List, Dict, Optional, Union
from datetime import datetime


class BaseDataModel(rx.Base):
    """Base data model with common fields."""
    id: str
    created_at: Union[str, datetime] = ""
    updated_at: Union[str, datetime] = ""
    is_active: bool = True


class OrganizationData(BaseDataModel):
    """Organization data model for frontend"""
    name: str
    description: str = ""
    subscription_plan: str = "basic"
    max_users: Optional[int] = 50
    max_projects: Optional[int] = 10
    admin_key: str = ""


class ProjectData(BaseDataModel):
    """Project data model for frontend"""
    name: str
    description: str = ""
    organization_id: str
    organization_name: str = ""
    status: str = "active"  # Standardized to use 'status' instead of 'is_active'
    
    @property
    def is_active(self) -> bool:
        """Compatibility property for is_active"""
        return self.status == "active"


class UserData(BaseDataModel):
    """User data model for frontend"""
    first_name: str
    last_name: str
    email: str
    organization_id: str
    organization_name: str = ""
    org_roles: List[str] = []
    project_assignments: List[Dict] = []
    
    @property
    def primary_role(self) -> str:
        """Get the primary role of the user"""
        if "super_admin" in self.org_roles:
            return "super_admin"
        elif "admin" in self.org_roles:
            return "admin"
        else:
            return "user"
    
    @property
    def role_display(self) -> str:
        """Get display-friendly role name"""
        role_map = {
            "super_admin": "Super Admin",
            "admin": "Admin",
            "user": "User"
        }
        return role_map.get(self.primary_role, "User")


class ProjectAssignmentData(rx.Base):
    """Project assignment data model"""
    user_id: str
    project_id: str
    project_name: str = ""
    roles: List[str] = []
    assigned_at: Union[str, datetime] = ""
    
    @property
    def roles_display(self) -> str:
        """Get comma-separated roles for display"""
        return ", ".join(self.roles)


# Role and status constants
class UserRoles:
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    
    @classmethod
    def get_all(cls) -> List[str]:
        return [cls.USER, cls.ADMIN, cls.SUPER_ADMIN]
    
    @classmethod
    def get_assignable(cls) -> List[str]:
        """Roles that can be assigned by admins (no super_admin)"""
        return [cls.USER, cls.ADMIN]
    
    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        return {
            cls.USER: "User",
            cls.ADMIN: "Admin",
            cls.SUPER_ADMIN: "Super Admin"
        }


class ProjectRoles:
    PROJECT_MANAGER = "project_manager"
    INSPECTOR = "inspector"
    ANALYST = "analyst"
    VIEWER = "viewer"
    
    @classmethod
    def get_all(cls) -> List[str]:
        return [cls.PROJECT_MANAGER, cls.INSPECTOR, cls.ANALYST, cls.VIEWER]
    
    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        return {
            cls.PROJECT_MANAGER: "Project Manager",
            cls.INSPECTOR: "Inspector",
            cls.ANALYST: "Analyst",
            cls.VIEWER: "Viewer"
        }


# Import centralized enum - alias for backward compatibility
from poseidon.backend.database.models.enums import SubscriptionPlan as SubscriptionPlans


class StatusTypes:
    ACTIVE = "active"
    INACTIVE = "inactive"
    ALL = "all"
    
    @classmethod
    def get_filter_options(cls) -> List[str]:
        return [cls.ACTIVE, cls.INACTIVE, cls.ALL]
    
    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        return {
            cls.ACTIVE: "Active",
            cls.INACTIVE: "Inactive",
            cls.ALL: "All"
        } 