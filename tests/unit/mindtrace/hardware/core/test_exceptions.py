"""Tests for hardware exceptions hierarchy."""

import pytest
from typing import Dict, Any

from mindtrace.hardware.core.exceptions import (
    # Base exceptions
    HardwareError,
    HardwareOperationError,
    HardwareTimeoutError,
    SDKNotAvailableError,
    
    # Camera exceptions
    CameraError,
    CameraNotFoundError,
    CameraInitializationError,
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraTimeoutError,
    
    # PLC exceptions
    PLCError,
    PLCNotFoundError,
    PLCConnectionError,
    PLCInitializationError,
    PLCCommunicationError,
    PLCTimeoutError,
    PLCConfigurationError,
    PLCTagError,
    PLCTagNotFoundError,
    PLCTagReadError,
    PLCTagWriteError,
)


class TestHardwareExceptions:
    """Test hardware exception hierarchy and behavior."""

    def test_hardware_error_base(self):
        """Test HardwareError base exception."""
        error = HardwareError("Test error message")
        
        assert str(error) == "Test error message"
        assert error.details == {}
        assert isinstance(error, Exception)

    def test_hardware_error_with_details(self):
        """Test HardwareError with details dictionary."""
        details = {"device_id": "CAM001", "error_code": 404}
        error = HardwareError("Device error", details=details)
        
        assert str(error) == "Device error"
        assert error.details == details
        assert error.details["device_id"] == "CAM001"

    def test_hardware_operation_error(self):
        """Test HardwareOperationError."""
        error = HardwareOperationError("Operation failed")
        
        assert isinstance(error, HardwareError)
        assert str(error) == "Operation failed"

    def test_hardware_timeout_error(self):
        """Test HardwareTimeoutError."""
        error = HardwareTimeoutError("Operation timed out")
        
        assert isinstance(error, HardwareError)
        assert str(error) == "Operation timed out"

    def test_sdk_not_available_error_basic(self):
        """Test SDKNotAvailableError with SDK name only."""
        error = SDKNotAvailableError("pypylon")
        
        assert isinstance(error, HardwareError)
        assert "pypylon" in str(error)
        assert error.sdk_name == "pypylon"
        assert error.installation_instructions is None

    def test_sdk_not_available_error_with_instructions(self):
        """Test SDKNotAvailableError with installation instructions."""
        instructions = "Install with: pip install pypylon"
        error = SDKNotAvailableError("pypylon", instructions)
        
        assert "pypylon" in str(error)
        assert instructions in str(error)
        assert error.sdk_name == "pypylon"
        assert error.installation_instructions == instructions

    def test_camera_error_hierarchy(self):
        """Test camera exception hierarchy."""
        # Base camera error
        error = CameraError("Camera error")
        assert isinstance(error, HardwareError)
        
        # Specific camera errors
        camera_errors = [
            CameraNotFoundError("Camera not found"),
            CameraInitializationError("Init failed"),
            CameraCaptureError("Capture failed"),
            CameraConfigurationError("Config failed"),
            CameraConnectionError("Connection failed"),
            CameraTimeoutError("Timeout"),
        ]
        
        for camera_error in camera_errors:
            assert isinstance(camera_error, CameraError)
            assert isinstance(camera_error, HardwareError)

    def test_plc_error_hierarchy(self):
        """Test PLC exception hierarchy."""
        # Base PLC error
        error = PLCError("PLC error")
        assert isinstance(error, HardwareError)
        
        # Specific PLC errors
        plc_errors = [
            PLCNotFoundError("PLC not found"),
            PLCConnectionError("Connection failed"),
            PLCInitializationError("Init failed"),
            PLCCommunicationError("Communication failed"),
            PLCTimeoutError("Timeout"),
            PLCConfigurationError("Config failed"),
        ]
        
        for plc_error in plc_errors:
            assert isinstance(plc_error, PLCError)
            assert isinstance(plc_error, HardwareError)

    def test_plc_tag_error_hierarchy(self):
        """Test PLC tag exception hierarchy."""
        # Base tag error
        error = PLCTagError("Tag error")
        assert isinstance(error, PLCError)
        assert isinstance(error, HardwareError)
        
        # Specific tag errors
        tag_errors = [
            PLCTagNotFoundError("Tag not found"),
            PLCTagReadError("Read failed"),
            PLCTagWriteError("Write failed"),
        ]
        
        for tag_error in tag_errors:
            assert isinstance(tag_error, PLCTagError)
            assert isinstance(tag_error, PLCError)
            assert isinstance(tag_error, HardwareError)

    def test_exception_with_context_manager(self):
        """Test exceptions work correctly with try/except blocks."""
        # Test specific exception catching
        with pytest.raises(CameraNotFoundError):
            raise CameraNotFoundError("Camera not available")
        
        # Test base class catching
        with pytest.raises(CameraError):
            raise CameraCaptureError("Capture failed")
        
        # Test root class catching
        with pytest.raises(HardwareError):
            raise PLCConnectionError("PLC unreachable")

    def test_exception_chaining(self):
        """Test exception chaining with cause and context."""
        try:
            raise ValueError("Original error")
        except ValueError as e:
            with pytest.raises(CameraInitializationError) as exc_info:
                raise CameraInitializationError("Camera init failed") from e
            
            # Check that the chain is preserved
            assert exc_info.value.__cause__ is e

    def test_exception_details_preserved(self):
        """Test that exception details are preserved through inheritance."""
        details = {
            "camera_name": "MockBasler_12345",
            "backend": "Basler",
            "error_code": "E_TIMEOUT",
            "timestamp": "2025-01-01T12:00:00Z"
        }
        
        error = CameraTimeoutError("Capture timeout", details=details)
        
        assert error.details == details
        assert error.details["camera_name"] == "MockBasler_12345"
        assert error.details["error_code"] == "E_TIMEOUT"

    def test_exception_str_representation(self):
        """Test string representation of exceptions."""
        test_cases = [
            (HardwareError("Hardware failed"), "Hardware failed"),
            (CameraNotFoundError("Camera missing"), "Camera missing"),
            (PLCTagReadError("Read failed"), "Read failed"),
            (SDKNotAvailableError("missing_sdk"), "SDK 'missing_sdk' is not available"),
        ]
        
        for exception, expected_str in test_cases:
            assert str(exception) == expected_str

    def test_exception_args_preserved(self):
        """Test that exception args are preserved."""
        message = "Test error message"
        error = CameraCaptureError(message)
        
        assert error.args == (message,)
        assert len(error.args) == 1
        assert error.args[0] == message

    def test_multiple_inheritance_compatibility(self):
        """Test that exceptions work with multiple catch blocks."""
        def raise_camera_error():
            raise CameraConnectionError("Connection lost")
        
        # Should be caught by specific handler
        try:
            raise_camera_error()
        except CameraConnectionError as e:
            assert "Connection lost" in str(e)
        except CameraError:
            pytest.fail("Should have been caught by specific handler")
        except HardwareError:
            pytest.fail("Should have been caught by specific handler")
        
        # Should be caught by base handler when specific is not present
        try:
            raise_camera_error()
        except CameraError as e:
            assert "Connection lost" in str(e)
        except HardwareError:
            pytest.fail("Should have been caught by CameraError handler")

    def test_custom_exception_attributes(self):
        """Test custom attributes on specific exceptions."""
        # SDKNotAvailableError has custom attributes
        error = SDKNotAvailableError("test_sdk", "Install instructions")
        assert hasattr(error, 'sdk_name')
        assert hasattr(error, 'installation_instructions')
        assert error.sdk_name == "test_sdk"

    def test_exception_equality(self):
        """Test exception equality comparison."""
        error1 = CameraError("Test error")
        error2 = CameraError("Test error")
        error3 = CameraError("Different error")
        
        # Exception equality is based on identity, not content
        assert error1 != error2  # Different instances
        assert error1 != error3  # Different messages

    def test_exception_type_checking(self):
        """Test exception type checking with isinstance."""
        error = CameraTimeoutError("Timeout occurred")
        
        # Should be instance of all parent classes
        assert isinstance(error, CameraTimeoutError)
        assert isinstance(error, CameraError)
        assert isinstance(error, HardwareError)
        assert isinstance(error, Exception)
        
        # Should not be instance of sibling classes
        assert not isinstance(error, PLCError)
        assert not isinstance(error, CameraCaptureError)

    def test_exception_subclass_checking(self):
        """Test exception subclass relationships."""
        # Test subclass relationships
        assert issubclass(CameraError, HardwareError)
        assert issubclass(CameraTimeoutError, CameraError)
        assert issubclass(PLCTagError, PLCError)
        assert issubclass(PLCTagReadError, PLCTagError)
        
        # Test non-relationships
        assert not issubclass(CameraError, PLCError)
        assert not issubclass(PLCError, CameraError)

    def test_exception_in_complex_scenarios(self):
        """Test exceptions in more complex error handling scenarios."""
        def simulate_hardware_operation(fail_type: str):
            """Simulate different failure types."""
            failures = {
                "camera_timeout": CameraTimeoutError("Camera response timeout"),
                "plc_connection": PLCConnectionError("PLC not reachable"),
                "sdk_missing": SDKNotAvailableError("required_sdk"),
                "general": HardwareOperationError("General failure"),
            }
            
            if fail_type in failures:
                raise failures[fail_type]
            return "success"
        
        # Test handling multiple error types
        error_counts = {"camera": 0, "plc": 0, "sdk": 0, "general": 0, "unknown": 0}
        
        for fail_type in ["camera_timeout", "plc_connection", "sdk_missing", "general"]:
            try:
                simulate_hardware_operation(fail_type)
            except CameraError:
                error_counts["camera"] += 1
            except PLCError:
                error_counts["plc"] += 1
            except SDKNotAvailableError:
                error_counts["sdk"] += 1
            except HardwareOperationError:
                error_counts["general"] += 1
            except HardwareError:
                error_counts["unknown"] += 1
        
        assert error_counts["camera"] == 1
        assert error_counts["plc"] == 1
        assert error_counts["sdk"] == 1
        assert error_counts["general"] == 1
        assert error_counts["unknown"] == 0

    def test_exception_details_mutation(self):
        """Test that exception details can be modified after creation."""
        error = HardwareError("Test", {"initial": "value"})
        
        # Details should be mutable
        error.details["additional"] = "info"
        error.details["initial"] = "modified"
        
        assert error.details["additional"] == "info"
        assert error.details["initial"] == "modified"
        assert len(error.details) == 2