"""Request models for sensor operations."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SensorConnectionRequest(BaseModel):
    """Request to connect to a sensor."""

    sensor_id: str = Field(..., description="Unique identifier for the sensor", min_length=1)
    backend_type: str = Field(..., description="Backend type (mqtt, http, serial)")
    config: Dict[str, Any] = Field(..., description="Backend-specific configuration")
    address: str = Field(..., description="Sensor address (topic, endpoint, or port)")

    class Config:
        json_schema_extra = {
            "example": {
                "sensor_id": "office_temp",
                "backend_type": "mqtt",
                "config": {"broker_url": "mqtt://localhost:1883", "identifier": "temp_reader"},
                "address": "sensors/office/temperature",
            }
        }


class SensorDataRequest(BaseModel):
    """Request to read data from a connected sensor."""

    sensor_id: str = Field(..., description="Unique identifier for the sensor", min_length=1)
    timeout: Optional[float] = Field(None, description="Read timeout in seconds")

    class Config:
        json_schema_extra = {"example": {"sensor_id": "office_temp", "timeout": 5.0}}


class SensorStatusRequest(BaseModel):
    """Request to get status of a sensor."""

    sensor_id: str = Field(..., description="Unique identifier for the sensor", min_length=1)

    class Config:
        json_schema_extra = {"example": {"sensor_id": "office_temp"}}


class SensorListRequest(BaseModel):
    """Request to list all sensors."""

    include_status: bool = Field(False, description="Include connection status for each sensor")

    class Config:
        json_schema_extra = {"example": {"include_status": True}}
