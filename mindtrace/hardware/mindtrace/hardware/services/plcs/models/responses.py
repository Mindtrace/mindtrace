"""
Response models for PLCManagerService.

Contains all Pydantic models for API responses, ensuring consistent
response formatting across all PLC management endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    """Base response model for all API endpoints."""

    success: bool
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BoolResponse(BaseResponse):
    """Response model for boolean operations."""

    data: bool


class StringResponse(BaseResponse):
    """Response model for string values."""

    data: str


class IntResponse(BaseResponse):
    """Response model for integer values."""

    data: int


class FloatResponse(BaseResponse):
    """Response model for float values."""

    data: float


class ListResponse(BaseResponse):
    """Response model for list data."""

    data: List[str]


class DictResponse(BaseResponse):
    """Response model for dictionary data."""

    data: Dict[str, Any]


# Backend & Discovery Responses
class BackendInfo(BaseModel):
    """Backend information model."""

    name: str
    available: bool
    type: str  # "hardware" or "mock"
    sdk_required: bool
    description: Optional[str] = None
    sdk_name: Optional[str] = None
    drivers: Optional[List[Dict[str, Any]]] = None


class BackendsResponse(BaseResponse):
    """Response model for backend listing."""

    data: List[str]  # List of backend names


class BackendInfoResponse(BaseResponse):
    """Response model for detailed backend information."""

    data: Dict[str, BackendInfo]


# PLC Information Models
class PLCInfo(BaseModel):
    """PLC information model."""

    name: str
    backend: str
    ip_address: str
    plc_type: Optional[str] = None
    active: bool
    connected: bool
    driver_type: Optional[str] = None
    product_name: Optional[str] = None
    product_type: Optional[str] = None
    vendor: Optional[str] = None
    revision: Optional[str] = None
    serial: Optional[str] = None


class PLCStatus(BaseModel):
    """PLC status model."""

    plc: str
    connected: bool
    initialized: bool
    backend: str
    ip_address: str
    plc_type: Optional[str] = None
    driver_type: Optional[str] = None
    error_count: int = 0


class PLCInfoResponse(BaseResponse):
    """Response model for PLC information."""

    data: PLCInfo


class PLCStatusResponse(BaseResponse):
    """Response model for PLC status."""

    data: PLCStatus


class ActivePLCsResponse(BaseResponse):
    """Response model for active PLCs listing."""

    data: List[str]  # List of active PLC names


# Tag Operation Responses
class TagReadResponse(BaseResponse):
    """Response model for tag read operations."""

    data: Dict[str, Any]  # {tag_name: value}


class TagWriteResponse(BaseResponse):
    """Response model for tag write operations."""

    data: Dict[str, bool]  # {tag_name: success}


class TagListResponse(BaseResponse):
    """Response model for tag list operations."""

    data: List[str]  # List of tag names


class TagInfo(BaseModel):
    """Tag information model."""

    name: str
    type: str
    description: Optional[str] = None
    size: int = 0
    driver: Optional[str] = None


class TagInfoResponse(BaseResponse):
    """Response model for tag information."""

    data: TagInfo


# Batch Operation Responses
class BatchOperationResult(BaseModel):
    """Batch operation result model."""

    successful: List[str]
    failed: List[str]
    results: Dict[str, Any]
    successful_count: int
    failed_count: int


class BatchOperationResponse(BaseResponse):
    """Response model for batch operations."""

    data: BatchOperationResult


class BatchTagReadResponse(BaseResponse):
    """Response model for batch tag read operations."""

    data: Dict[str, Dict[str, Any]]  # {plc_name: {tag_name: value}}
    successful_count: int = 0
    failed_count: int = 0


class BatchTagWriteResponse(BaseResponse):
    """Response model for batch tag write operations."""

    data: Dict[str, Dict[str, bool]]  # {plc_name: {tag_name: success}}
    successful_count: int = 0
    failed_count: int = 0


# System Diagnostics
class SystemDiagnostics(BaseModel):
    """System diagnostics model."""

    active_plcs: int
    connected_plcs: int
    backend_status: Dict[str, bool]
    uptime_seconds: float
    total_tag_reads: int = 0
    total_tag_writes: int = 0


class SystemDiagnosticsResponse(BaseResponse):
    """Response model for system diagnostics."""

    data: SystemDiagnostics
