"""
Request models for PLCManagerService.

Contains all Pydantic models for API requests, ensuring proper
input validation and documentation for all PLC operations.
"""

from typing import Any, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator


# Backend & Discovery Operations
class BackendFilterRequest(BaseModel):
    """Request model for backend filtering."""

    backend: Optional[str] = Field(None, description="Backend name to filter by (AllenBradley, Siemens, Modbus)")


# PLC Lifecycle Operations
class PLCConnectRequest(BaseModel):
    """Request model for connecting to a PLC."""

    plc_name: str = Field(..., description="Unique identifier for the PLC")
    backend: str = Field(..., description="Backend type (AllenBradley, Siemens, Modbus)")
    ip_address: str = Field(..., description="IP address of the PLC")
    plc_type: Optional[str] = Field(None, description="Specific PLC type (logix, slc, cip, auto)")
    connection_timeout: Optional[float] = Field(None, description="Connection timeout in seconds")
    read_timeout: Optional[float] = Field(None, description="Tag read timeout in seconds")
    write_timeout: Optional[float] = Field(None, description="Tag write timeout in seconds")
    retry_count: Optional[int] = Field(None, description="Number of retry attempts")
    retry_delay: Optional[float] = Field(None, description="Delay between retries in seconds")


class PLCConnectBatchRequest(BaseModel):
    """Request model for batch PLC connection."""

    plcs: List[PLCConnectRequest] = Field(..., description="List of PLCs to connect")


class PLCDisconnectRequest(BaseModel):
    """Request model for disconnecting from a PLC."""

    plc: str = Field(..., description="PLC name to disconnect")


class PLCDisconnectBatchRequest(BaseModel):
    """Request model for batch PLC disconnection."""

    plcs: List[str] = Field(..., description="List of PLC names to disconnect")


class PLCQueryRequest(BaseModel):
    """Request model for PLC query operations."""

    plc: str = Field(..., description="PLC name")


# Tag Operations
class TagReadRequest(BaseModel):
    """Request model for reading tags from a PLC."""

    plc: str = Field(..., description="PLC name")
    tags: Union[str, List[str]] = Field(..., description="Single tag name or list of tag names")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Union[str, List[str]]) -> Union[str, List[str]]:
        """Ensure tags is not empty."""
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("Tags list cannot be empty")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Tag name cannot be empty")
        return v


class TagWriteRequest(BaseModel):
    """Request model for writing tags to a PLC."""

    plc: str = Field(..., description="PLC name")
    tags: Union[Tuple[str, Any], List[Tuple[str, Any]]] = Field(
        ..., description="Single (tag_name, value) tuple or list of tuples"
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(
        cls, v: Union[Tuple[str, Any], List[Tuple[str, Any]]]
    ) -> Union[Tuple[str, Any], List[Tuple[str, Any]]]:
        """Ensure tags is properly formatted."""
        if isinstance(v, list):
            if len(v) == 0:
                raise ValueError("Tags list cannot be empty")
            for item in v:
                if not isinstance(item, (tuple, list)) or len(item) != 2:
                    raise ValueError("Each tag write must be a (name, value) tuple")
        elif isinstance(v, (tuple, list)):
            if len(v) != 2:
                raise ValueError("Tag write must be a (name, value) tuple")
        else:
            raise ValueError("Tags must be a tuple or list of tuples")
        return v


class TagBatchReadRequest(BaseModel):
    """Request model for batch tag reading from multiple PLCs."""

    requests: List[Tuple[str, Union[str, List[str]]]] = Field(
        ..., description="List of (plc_name, tags) tuples for batch reading"
    )

    @field_validator("requests")
    @classmethod
    def validate_requests(cls, v: List[Tuple[str, Union[str, List[str]]]]) -> List[Tuple[str, Union[str, List[str]]]]:
        """Validate batch read requests."""
        if len(v) == 0:
            raise ValueError("Batch requests cannot be empty")
        for item in v:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError("Each request must be a (plc_name, tags) tuple")
        return v


class TagBatchWriteRequest(BaseModel):
    """Request model for batch tag writing to multiple PLCs."""

    requests: List[Tuple[str, Union[Tuple[str, Any], List[Tuple[str, Any]]]]] = Field(
        ..., description="List of (plc_name, tags) tuples for batch writing"
    )

    @field_validator("requests")
    @classmethod
    def validate_requests(
        cls, v: List[Tuple[str, Union[Tuple[str, Any], List[Tuple[str, Any]]]]]
    ) -> List[Tuple[str, Union[Tuple[str, Any], List[Tuple[str, Any]]]]]:
        """Validate batch write requests."""
        if len(v) == 0:
            raise ValueError("Batch requests cannot be empty")
        for item in v:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError("Each request must be a (plc_name, tags) tuple")
        return v


class TagInfoRequest(BaseModel):
    """Request model for getting tag information."""

    plc: str = Field(..., description="PLC name")
    tag: str = Field(..., description="Tag name to get information for")
