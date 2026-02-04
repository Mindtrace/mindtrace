"""Project License Model

Defines the ProjectLicense model for the simple binary license system.
Each project has one license that gates all functionality.
"""

from datetime import datetime, UTC
from typing import TYPE_CHECKING

from beanie import Document, Link
from pydantic import Field
from mindtrace.database import MindtraceDocument

from .enums import LicenseStatus

if TYPE_CHECKING:
    from .user import User
    from .project import Project
    from .organization import Organization


class ProjectLicense(MindtraceDocument):
    """Project license for binary access control.
    
    Simple licensing model where having a valid license grants full access
    to all project features, while invalid/expired licenses restrict access.
    """
    
    # Core license data
    project: Link["Project"] = Field(description="Project this license applies to")
    license_key: str = Field(description="Unique license identifier", index=True)
    status: LicenseStatus = Field(default=LicenseStatus.ACTIVE, description="Current license status")
    
    # Timestamps
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="When license was issued")
    expires_at: datetime = Field(description="License expiration date")
    
    # Management tracking
    issued_by: Link["User"] = Field(description="Super admin who issued the license")
    organization: Link["Organization"] = Field(description="Organization for tracking and validation")
    
    # Optional metadata
    notes: str = Field(default="", description="Optional notes about the license")
    
    class Settings:
        name = "project_licenses"
        indexes = [
            "license_key",
            "project",
            "organization",
            "status",
            "expires_at"
        ]
    
    @property
    def is_valid(self) -> bool:
        """Check if license is currently valid for full functionality"""
        if self.status != LicenseStatus.ACTIVE:
            return False
        
        # Check expiration
        if self.expires_at:
            # Ensure both datetimes are timezone-aware for comparison
            now = datetime.now(UTC)
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if now > expires:
                return False
            
        return True
    
    @property
    def is_expired(self) -> bool:
        """Check if license has expired"""
        if not self.expires_at:
            return False
        
        # Ensure both datetimes are timezone-aware for comparison
        now = datetime.now(UTC)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return now > expires
    
    @property
    def days_until_expiry(self) -> int:
        """Get days until license expires (negative if already expired)"""
        if not self.expires_at:
            return 999999  # No expiration
        
        # Ensure both datetimes are timezone-aware for comparison
        now = datetime.now(UTC)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        delta = expires - now
        return delta.days
    
    @property
    def status_display(self) -> str:
        """Get human-readable status display"""
        if self.is_expired and self.status == LicenseStatus.ACTIVE:
            return "Expired"
        return LicenseStatus.get_display_names().get(self.status, self.status)