"""License models for offline license validation."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class LicenseType(str, Enum):
    """License type enumeration."""

    TRIAL = "trial"
    STANDARD = "standard"
    ENTERPRISE = "enterprise"


class LicenseStatus(str, Enum):
    """License validation status."""

    VALID = "valid"
    EXPIRED = "expired"
    INVALID_SIGNATURE = "invalid_signature"
    HARDWARE_MISMATCH = "hardware_mismatch"
    NOT_ACTIVATED = "not_activated"


@dataclass
class License:
    """Internal license representation."""

    id: str
    license_key: str
    license_type: str
    machine_id: str
    issued_at: datetime
    expires_at: datetime
    features: List[str]
    max_users: int
    max_plants: int
    max_lines: int
    signature: str
    is_active: bool = True


# Request/Response models


class LicenseActivateRequest(BaseModel):
    """Request to activate a license."""

    license_file: str = Field(
        ..., description="Base64-encoded signed license file content"
    )


class LicenseResponse(BaseModel):
    """API response for license info."""

    id: str = Field(..., description="License record ID")
    license_key: str = Field(..., description="License key")
    license_type: str = Field(..., description="License type")
    machine_id: str = Field(..., description="Bound machine ID")
    issued_at: datetime = Field(..., description="Issue timestamp")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    features: List[str] = Field(..., description="Enabled features")
    max_users: int = Field(..., description="Maximum allowed users")
    max_plants: int = Field(..., description="Maximum allowed plants")
    max_lines: int = Field(..., description="Maximum allowed lines")
    is_active: bool = Field(..., description="Whether license is active")
    status: LicenseStatus = Field(..., description="Current license status")
    days_remaining: int = Field(..., description="Days until expiration")


class LicenseValidationResponse(BaseModel):
    """Response from license validation."""

    is_valid: bool = Field(..., description="Whether the license is valid")
    status: LicenseStatus = Field(..., description="License status")
    message: str = Field(..., description="Human-readable status message")
    days_remaining: Optional[int] = Field(None, description="Days until expiration")
    features: List[str] = Field(default_factory=list, description="Enabled features")


class MachineIdResponse(BaseModel):
    """Response containing the machine ID."""

    machine_id: str = Field(..., description="This machine's unique hardware ID")


class LicenseFile(BaseModel):
    """Structure of a license file payload (before signing)."""

    license_key: str = Field(..., description="Unique license key")
    license_type: str = Field(..., description="License type")
    issued_at: str = Field(..., description="Issue timestamp (ISO format)")
    expires_at: str = Field(..., description="Expiration timestamp (ISO format)")
    features: List[str] = Field(..., description="Enabled features")
    max_users: int = Field(..., description="Maximum allowed users")
    max_plants: int = Field(..., description="Maximum allowed plants")
    max_lines: int = Field(..., description="Maximum allowed lines")
    allowed_machine_ids: List[str] = Field(
        ..., description="Machine IDs this license is valid for"
    )


class SignedLicenseFile(BaseModel):
    """Complete signed license file."""

    payload: LicenseFile = Field(..., description="License payload")
    signature: str = Field(..., description="HMAC-SHA256 signature of payload")
