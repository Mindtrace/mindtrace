from enum import Enum
from typing import Dict, List


class SubscriptionPlan(str, Enum):
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"
    
    @classmethod
    def get_all(cls) -> List[str]:
        return [cls.BASIC, cls.PREMIUM, cls.ENTERPRISE]
    
    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        return {
            cls.BASIC: "Basic",
            cls.PREMIUM: "Premium",
            cls.ENTERPRISE: "Enterprise"
        }

class OrgRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    
    @classmethod
    def is_admin(cls, role) -> bool:
        """Check if role is admin (excludes super admin)"""
        return role == cls.ADMIN
    
    @classmethod
    def is_super_admin(cls, role) -> bool:
        """Check if role is super admin"""
        return role == cls.SUPER_ADMIN
    
    @classmethod
    def is_admin_or_higher(cls, role) -> bool:
        """Check if role is admin or super admin"""
        return role in (cls.ADMIN, cls.SUPER_ADMIN)
    
    @classmethod
    def get_manageable_roles(cls) -> List[str]:
        """Get roles that can be managed by admins"""
        return [cls.USER, cls.ADMIN]

class ProjectRole(str, Enum):
    INSPECTOR = "inspector"
    VIEWER = "viewer"

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class ProjectType(str, Enum):
    INSPECTION = "inspection"
    AUDIT = "audit"
    OTHER = "other"

from enum import Enum

class ModelValidationStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED = "failed"

class DeploymentStatus(str, Enum):
    PENDING = "pending"
    DEPLOYED = "deployed"
    FAILED = "failed"

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class CameraStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

class ScanStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ScanImageStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"

class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    
    @classmethod
    def is_valid(cls, status) -> bool:
        """Check if license status allows full functionality"""
        return status == cls.ACTIVE
    
    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        return {
            cls.ACTIVE: "Active",
            cls.EXPIRED: "Expired", 
            cls.CANCELLED: "Cancelled"
        }