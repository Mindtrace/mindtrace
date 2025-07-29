"""
Hardware Exception Hierarchy

This module defines the exception hierarchy for hardware operations including
cameras, PLCs, sensors, and other hardware components. Only actively used
exceptions are included to maintain a clean codebase.

Exception Hierarchy:
    HardwareError (base)
    ├── HardwareOperationError (general hardware operations)
    ├── HardwareTimeoutError (timeout operations)
    ├── SDKNotAvailableError (SDK availability)
    ├── CameraError (camera-specific base)
    │   ├── CameraNotFoundError
    │   ├── CameraInitializationError
    │   ├── CameraCaptureError
    │   ├── CameraConfigurationError
    │   ├── CameraConnectionError
    │   └── CameraTimeoutError
    ├── PLCError (PLC-specific base)
    │   ├── PLCNotFoundError
    │   ├── PLCConnectionError
    │   ├── PLCInitializationError
    │   ├── PLCCommunicationError
    │   ├── PLCTimeoutError
    │   ├── PLCConfigurationError
    │   └── PLCTagError (tag-specific base)
    │       ├── PLCTagNotFoundError
    │       ├── PLCTagReadError
    │       └── PLCTagWriteError
    └── SensorError (sensor-specific base, reserved for future use)
"""

from typing import Any, Dict, Optional


# Base hardware exception
class HardwareError(Exception):
    """Base exception for all hardware-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class HardwareOperationError(HardwareError):
    """Raised when a general hardware operation fails."""

    pass


class HardwareTimeoutError(HardwareError):
    """Raised when a hardware operation times out."""

    pass


class SDKNotAvailableError(HardwareError):
    """Raised when a required SDK is not available or not installed."""

    def __init__(self, sdk_name: str, installation_instructions: Optional[str] = None):
        message = f"SDK '{sdk_name}' is not available"
        if installation_instructions:
            message += f"\n\nInstallation instructions:\n{installation_instructions}"
        super().__init__(message)
        self.sdk_name = sdk_name
        self.installation_instructions = installation_instructions


# Camera-specific exceptions
class CameraError(HardwareError):
    """Base exception for camera-related errors."""

    pass


class CameraNotFoundError(CameraError):
    """Raised when camera is not found or not available."""

    pass


class CameraInitializationError(CameraError):
    """Raised when camera fails to initialize."""

    pass


class CameraCaptureError(CameraError):
    """Raised when camera capture operation fails."""

    pass


class CameraConfigurationError(CameraError):
    """Raised when camera configuration is invalid."""

    pass


class CameraConnectionError(CameraError):
    """Raised when camera connection fails."""

    pass


class CameraTimeoutError(CameraError):
    """Raised when camera operation times out."""

    pass


# Sensor-specific exceptions (reserved for future use)
class SensorError(HardwareError):
    """Base exception for sensor-related errors."""

    pass


# PLC-specific exceptions
class PLCError(HardwareError):
    """Base exception for PLC-related errors."""

    pass


class PLCNotFoundError(PLCError):
    """Raised when PLC is not found or not available."""

    pass


class PLCConnectionError(PLCError):
    """Raised when PLC connection fails."""

    pass


class PLCInitializationError(PLCError):
    """Raised when PLC fails to initialize."""

    pass


class PLCCommunicationError(PLCError):
    """Raised when PLC communication fails."""

    pass


class PLCTagError(PLCError):
    """Base exception for PLC tag-related errors."""

    pass


class PLCTagNotFoundError(PLCTagError):
    """Raised when PLC tag is not found."""

    pass


class PLCTagReadError(PLCTagError):
    """Raised when PLC tag read operation fails."""

    pass


class PLCTagWriteError(PLCTagError):
    """Raised when PLC tag write operation fails."""

    pass


class PLCTimeoutError(PLCError):
    """Raised when PLC operation times out."""

    pass


class PLCConfigurationError(PLCError):
    """Raised when PLC configuration is invalid."""

    pass
