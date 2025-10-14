"""Response models for sensor operations."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SensorConnectionStatus(str, Enum):
    """Status of sensor connection."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class SensorInfo(BaseModel):
    """Information about a sensor."""

    sensor_id: str = Field(..., description="Unique identifier for the sensor", min_length=1)
    backend_type: str = Field(..., description="Backend type (mqtt, http, serial)")
    address: str = Field(..., description="Sensor address (topic, endpoint, or port)")
    status: SensorConnectionStatus = Field(..., description="Connection status")
    last_data_time: Optional[float] = Field(None, description="Timestamp of last data read")

    class Config:
        json_schema_extra = {
            "example": {
                "sensor_id": "office_temp",
                "backend_type": "mqtt",
                "address": "sensors/office/temperature",
                "status": "connected",
                "last_data_time": 1640995200.0,
            }
        }


class SensorConnectionResponse(BaseModel):
    """Response from sensor connection operation."""

    success: bool = Field(..., description="Whether connection was successful")
    sensor_id: str = Field(..., description="Unique identifier for the sensor", min_length=1)
    status: SensorConnectionStatus = Field(..., description="Connection status")
    message: Optional[str] = Field(None, description="Additional information or error message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "sensor_id": "office_temp",
                "status": "connected",
                "message": "Successfully connected to MQTT sensor",
            }
        }


class SensorDataResponse(BaseModel):
    """Response containing sensor data."""

    success: bool = Field(..., description="Whether data read was successful")
    sensor_id: str = Field(..., description="Unique identifier for the sensor", min_length=1)
    data: Optional[Dict[str, Any]] = Field(None, description="Sensor data payload")
    timestamp: Optional[float] = Field(None, description="Timestamp when data was read")
    message: Optional[str] = Field(None, description="Additional information or error message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "sensor_id": "office_temp",
                "data": {"temperature": 23.5, "humidity": 45.2, "timestamp": 1640995200},
                "timestamp": 1640995200.0,
                "message": "Data read successfully",
            }
        }


class SensorStatusResponse(BaseModel):
    """Response containing sensor status information."""

    success: bool = Field(..., description="Whether status check was successful")
    sensor_info: Optional[SensorInfo] = Field(None, description="Sensor information")
    message: Optional[str] = Field(None, description="Additional information or error message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "sensor_info": {
                    "sensor_id": "office_temp",
                    "backend_type": "mqtt",
                    "address": "sensors/office/temperature",
                    "status": "connected",
                    "last_data_time": 1640995200.0,
                },
                "message": "Status retrieved successfully",
            }
        }


class SensorListResponse(BaseModel):
    """Response containing list of sensors."""

    success: bool = Field(..., description="Whether list operation was successful")
    sensors: List[SensorInfo] = Field(..., description="List of sensor information")
    count: int = Field(..., description="Number of sensors")
    message: Optional[str] = Field(None, description="Additional information")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "sensors": [
                    {
                        "sensor_id": "office_temp",
                        "backend_type": "mqtt",
                        "address": "sensors/office/temperature",
                        "status": "connected",
                        "last_data_time": 1640995200.0,
                    }
                ],
                "count": 1,
                "message": "Retrieved 1 sensors",
            }
        }
