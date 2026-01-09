"""Beanie Document models for Inspectra MongoDB collections.

This module defines MindtraceDocument subclasses that map to MongoDB collections.
These replace the dataclass models and provide ODM functionality via Beanie.
"""

from datetime import datetime
from typing import Any, List, Optional

from beanie import Indexed
from pydantic import Field

from mindtrace.database import MindtraceDocument


class UserDocument(MindtraceDocument):
    """User document for authentication and authorization."""

    username: Indexed(str, unique=True)
    password_hash: str
    role_id: Indexed(str)
    plant_id: Optional[str] = None
    is_active: bool = True

    class Settings:
        name = "users"
        use_cache = False
        indexes = [
            "plant_id",
            "is_active",
        ]


class RoleDocument(MindtraceDocument):
    """Role document for RBAC permissions."""

    name: Indexed(str, unique=True)
    description: Optional[str] = None
    permissions: Optional[List[str]] = None

    class Settings:
        name = "roles"
        use_cache = False


class PlantDocument(MindtraceDocument):
    """Plant/Organization document."""

    name: str
    code: Indexed(str, unique=True)
    location: Optional[str] = None
    is_active: bool = True

    class Settings:
        name = "plants"
        use_cache = False
        indexes = [
            "is_active",
        ]


class LineDocument(MindtraceDocument):
    """Production line document."""

    name: str
    plant_id: Optional[str] = None

    class Settings:
        name = "lines"
        use_cache = False
        indexes = [
            "plant_id",
            [("plant_id", 1), ("name", 1)],
        ]


class PolicyRuleDocument(MindtraceDocument):
    """Password policy rule document."""

    policy_id: Indexed(str)
    rule_type: str
    value: Any = Field(..., description="Rule value (int, bool, or str)")
    message: str
    is_active: bool = True
    order: int = 0

    class Settings:
        name = "policy_rules"
        use_cache = False


class PasswordPolicyDocument(MindtraceDocument):
    """Password policy document."""

    name: str
    description: Optional[str] = None
    is_active: bool = True
    is_default: bool = False

    class Settings:
        name = "password_policies"
        use_cache = False
        indexes = [
            "is_active",
            [("is_default", 1), ("is_active", 1)],
        ]


class LicenseDocument(MindtraceDocument):
    """License document for offline validation."""

    license_key: Indexed(str, unique=True)
    license_type: str
    machine_id: str
    issued_at: datetime
    expires_at: datetime
    features: List[str] = Field(default_factory=list)
    max_users: int = 0
    max_plants: int = 0
    max_lines: int = 0
    signature: str
    is_active: bool = True

    class Settings:
        name = "licenses"
        use_cache = False
        indexes = [
            "is_active",
        ]


__all__ = [
    "UserDocument",
    "RoleDocument",
    "PlantDocument",
    "LineDocument",
    "PolicyRuleDocument",
    "PasswordPolicyDocument",
    "LicenseDocument",
]
