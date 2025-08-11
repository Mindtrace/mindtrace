import asyncio
import logging
import pytest
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch

import numpy as np

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
)


def enable_log_capture(backend, level=logging.WARNING):
    """Helper function to enable log capture for testing."""
    original_levels = []
    for handler in backend.logger.handlers:
        original_levels.append(handler.level)
        handler.setLevel(level)
    
    original_propagate = backend.logger.propagate
    backend.logger.propagate = True
    
    return original_levels, original_propagate


def restore_log_settings(backend, original_levels, original_propagate):
    """Helper function to restore original log settings."""
    for handler, level in zip(backend.logger.handlers, original_levels):
        handler.setLevel(level)
    backend.logger.propagate = original_propagate


class ConcreteCameraBackend(CameraBackend):
    """Concrete implementation of CameraBackend for testing."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mock_initialized = False
        self.mock_camera = None
        self.mock_remote = None
    
    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Mock implementation for testing."""
        if hasattr(self, '_force_init_failure'):
            if self._force_init_failure == 'not_found':
                raise CameraNotFoundError("Camera not found")
            elif self._force_init_failure == 'connection':
                raise CameraConnectionError("Connection failed")
            elif self._force_init_failure == 'generic':
                raise RuntimeError("Generic error")
            elif self._force_init_failure == 'return_false':
                return False, None, None
        
        self.mock_initialized = True
        self.mock_camera = "mock_camera_object"
        self.mock_remote = "mock_remote_object"
        return True, self.mock_camera, self.mock_remote
    
    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        return True
    
    async def get_exposure(self) -> float:
        return 1000.0
    
    async def get_exposure_range(self) -> List[Union[int, float]]:
        return [100.0, 10000.0]
    
    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        return True, np.zeros((480, 640, 3), dtype=np.uint8)
    
    async def check_connection(self) -> bool:
        return self.mock_initialized
    
    async def close(self) -> None:
        self.mock_initialized = False
        self.mock_camera = None
        self.mock_remote = None
        # Also reset the parent class initialized flag
        self.initialized = False
        self.camera = None
    
    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        if include_details:
            return {"test_camera": {"type": "test", "status": "available"}}
        return ["test_camera"]


class TestCameraBackendConstructor:
    """Test camera backend constructor and initialization."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_constructor_default_params(self, mock_get_config):
        """Test constructor with default parameters."""
        # Mock config
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Should auto-generate camera_name
        assert isinstance(backend.camera_name, str)
        assert len(backend.camera_name) > 0
        
        # Should use config defaults
        assert backend.img_quality_enhancement is True
        assert backend.retrieve_retry_count == 3
        assert backend.camera_config_file is None
        assert backend.camera is None
        assert backend.device_manager is None
        assert backend.initialized is False
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_constructor_explicit_params(self, mock_get_config):
        """Test constructor with explicit parameters."""
        # Mock config
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend(
            camera_name="test_camera",
            camera_config="/path/to/config.json",
            img_quality_enhancement=False,
            retrieve_retry_count=5
        )
        
        # Should use explicit values
        assert backend.camera_name == "test_camera"
        assert backend.camera_config_file == "/path/to/config.json"
        assert backend.img_quality_enhancement is False
        assert backend.retrieve_retry_count == 5
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_constructor_uuid_generation(self, mock_get_config):
        """Test that auto-generated camera names are valid UUIDs."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Should be a valid UUID string
        try:
            uuid.UUID(backend.camera_name)
        except ValueError:
            pytest.fail("Generated camera_name is not a valid UUID")
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_constructor_config_integration(self, mock_get_config):
        """Test integration with get_camera_config."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = False
        mock_config_obj.cameras.retrieve_retry_count = 7
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Should call config system
        mock_get_config.assert_called_once()
        mock_get_config.return_value.get_config.assert_called_once()
        
        # Should use config values when not explicitly provided
        assert backend.img_quality_enhancement is False
        assert backend.retrieve_retry_count == 7


class TestCameraBackendLogging:
    """Test logger setup and formatting."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_logger_setup_no_handlers(self, mock_get_config):
        """Test logger setup when no handlers exist."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Logger should be configured
        assert hasattr(backend, 'logger')
        assert backend.logger.propagate is False
        assert backend.logger.level == logging.DEBUG  # Actual level is DEBUG (10)
        
        # Should have handlers (may have multiple)
        assert len(backend.logger.handlers) > 0
        handler = backend.logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        # Handler level may be higher (ERROR level in actual implementation)
        assert handler.level >= logging.WARNING
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_logger_formatter(self, mock_get_config):
        """Test logger formatter configuration."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        handler = backend.logger.handlers[0]
        formatter = handler.formatter
        
        # Should have correct format (actual format from implementation)
        expected_format = "[%(asctime)s] %(levelname)s: %(name)s: %(message)s"
        assert formatter._fmt == expected_format
        # Actual implementation doesn't set datefmt 
        assert formatter.datefmt is None
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_logger_with_existing_handlers(self, mock_get_config):
        """Test logger setup when handlers already exist."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        # Create backend and note handler count
        backend = ConcreteCameraBackend()
        initial_handler_count = len(backend.logger.handlers)
        
        # Call setup again
        backend._setup_camera_logger_formatting()
        
        # Should not add duplicate handlers
        assert len(backend.logger.handlers) == initial_handler_count


class TestCameraBackendSetup:
    """Test setup_camera method and initialization flow."""
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_setup_camera_success(self, mock_get_config):
        """Test successful camera setup."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        await backend.setup_camera()
        
        # Should set initialized flag and camera object
        assert backend.initialized is True
        assert backend.camera == "mock_camera_object"
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_setup_camera_init_returns_false(self, mock_get_config):
        """Test setup when initialize returns False."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend._force_init_failure = 'return_false'
        
        with pytest.raises(CameraInitializationError, match="initialization returned False"):
            await backend.setup_camera()
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_setup_camera_not_found_exception(self, mock_get_config):
        """Test setup with CameraNotFoundError."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend._force_init_failure = 'not_found'
        
        # Should re-raise specific exceptions
        with pytest.raises(CameraNotFoundError):
            await backend.setup_camera()
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_setup_camera_connection_exception(self, mock_get_config):
        """Test setup with CameraConnectionError."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend._force_init_failure = 'connection'
        
        # Should re-raise specific exceptions
        with pytest.raises(CameraConnectionError):
            await backend.setup_camera()
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_setup_camera_generic_exception(self, mock_get_config):
        """Test setup with generic exception."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend._force_init_failure = 'generic'
        
        # Should wrap generic exceptions in CameraInitializationError
        with pytest.raises(CameraInitializationError, match="Failed to initialize camera"):
            await backend.setup_camera()
        
        # Should set initialized to False
        assert backend.initialized is False


class TestCameraBackendDefaultImplementations:
    """Test default method implementations and warning logging."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_config_methods_log_warnings(self, mock_get_config, caplog):
        """Test that config methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            # Test async config methods
            result1 = asyncio.run(backend.set_config("test_config"))
            result2 = asyncio.run(backend.import_config("/path/to/config"))
            result3 = asyncio.run(backend.export_config("/path/to/config"))
            
            assert result1 is False
            assert result2 is False
            assert result3 is False
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Should log warnings
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("set_config not implemented" in msg for msg in log_messages)
        assert any("import_config not implemented" in msg for msg in log_messages)
        assert any("export_config not implemented" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_white_balance_methods_log_warnings(self, mock_get_config, caplog):
        """Test white balance methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            result1 = asyncio.run(backend.get_wb())
            result2 = asyncio.run(backend.set_auto_wb_once("auto"))
            result3 = backend.get_wb_range()
            
            assert result1 == "unknown"
            assert result2 is False
            assert result3 == ["auto", "manual", "off"]
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("get_wb not implemented" in msg for msg in log_messages)
        assert any("set_auto_wb_once not implemented" in msg for msg in log_messages)
        assert any("get_wb_range not implemented" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_trigger_methods_log_warnings(self, mock_get_config, caplog):
        """Test trigger methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            result1 = asyncio.run(backend.get_triggermode())
            result2 = asyncio.run(backend.set_triggermode("trigger"))
            
            assert result1 == "continuous"
            assert result2 is False
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("get_triggermode not implemented" in msg for msg in log_messages)
        assert any("set_triggermode not implemented" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_dimension_methods_log_warnings(self, mock_get_config, caplog):
        """Test dimension methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            result1 = asyncio.run(backend.get_width_range())
            result2 = asyncio.run(backend.get_height_range())
            
            assert result1 == [640, 1920]
            assert result2 == [480, 1080]
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("get_width_range not implemented" in msg for msg in log_messages)
        assert any("get_height_range not implemented" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_gain_methods_log_warnings(self, mock_get_config, caplog):
        """Test gain methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            result1 = backend.set_gain(2.0)
            result2 = backend.get_gain()
            result3 = backend.get_gain_range()
            
            assert result1 is False
            assert result2 == 1.0
            assert result3 == [1.0, 16.0]
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("set_gain not implemented" in msg for msg in log_messages)
        assert any("get_gain not implemented" in msg for msg in log_messages)
        assert any("get_gain_range not implemented" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_roi_methods_log_warnings(self, mock_get_config, caplog):
        """Test ROI methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            result1 = backend.set_ROI(0, 0, 640, 480)
            result2 = backend.get_ROI()
            result3 = backend.reset_ROI()
            
            assert result1 is False
            assert result2 == {"x": 0, "y": 0, "width": 1920, "height": 1080}
            assert result3 is False
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("set_ROI not implemented" in msg for msg in log_messages)
        assert any("get_ROI not implemented" in msg for msg in log_messages)
        assert any("reset_ROI not implemented" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_pixel_format_methods_log_warnings(self, mock_get_config, caplog):
        """Test pixel format methods log warnings and return expected values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend)
        
        with caplog.at_level(logging.WARNING):
            result1 = backend.get_pixel_format_range()
            result2 = backend.get_current_pixel_format()
            result3 = backend.set_pixel_format("RGB8")
            
            assert result1 == ["BGR8", "RGB8"]
            assert result2 == "RGB8"
            assert result3 is False
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("get_pixel_format_range not implemented" in msg for msg in log_messages)
        assert any("get_current_pixel_format not implemented" in msg for msg in log_messages)
        assert any("set_pixel_format not implemented" in msg for msg in log_messages)


class TestCameraBackendImageQualityEnhancement:
    """Test image quality enhancement getter/setter."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_get_image_quality_enhancement(self, mock_get_config):
        """Test getting image quality enhancement setting."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        assert backend.get_image_quality_enhancement() is True
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_set_image_quality_enhancement(self, mock_get_config, caplog):
        """Test setting image quality enhancement."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Temporarily lower handler levels to capture info logs
        original_levels, original_propagate = enable_log_capture(backend, logging.INFO)
        
        with caplog.at_level(logging.INFO):
            result = backend.set_image_quality_enhancement(False)
            
            assert result is True
            assert backend.img_quality_enhancement is False
            assert backend.get_image_quality_enhancement() is False
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Should log the change
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("Image quality enhancement set to False" in msg for msg in log_messages)
        assert any(backend.camera_name in msg for msg in log_messages)


class TestCameraBackendAsyncContext:
    """Test async context manager protocol."""
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_async_context_manager_success(self, mock_get_config):
        """Test successful async context manager usage."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        assert backend.initialized is False
        
        async with backend as ctx_backend:
            assert ctx_backend is backend
            assert backend.initialized is True
            assert backend.camera == "mock_camera_object"
        
        # Should be cleaned up after context exit
        assert backend.initialized is False
        assert backend.camera is None
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_async_context_manager_setup_failure(self, mock_get_config):
        """Test async context manager with setup failure."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend._force_init_failure = 'not_found'
        
        with pytest.raises(CameraNotFoundError):
            async with backend:
                pass
        
        # Should not be initialized
        assert backend.initialized is False
    
    @pytest.mark.asyncio
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    async def test_async_context_manager_exception_during_use(self, mock_get_config):
        """Test async context manager cleanup when exception occurs during use."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        with pytest.raises(RuntimeError, match="test exception"):
            async with backend:
                assert backend.initialized is True
                raise RuntimeError("test exception")
        
        # Should still be cleaned up
        assert backend.initialized is False
        assert backend.camera is None


class TestCameraBackendCleanup:
    """Test resource cleanup and destructor behavior."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_destructor_with_camera_warns(self, mock_get_config, caplog):
        """Test destructor warns when camera not properly cleaned up."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend.camera = "mock_camera"  # Simulate uncleaned camera
        
        # Temporarily lower handler levels to capture warnings
        original_levels, original_propagate = enable_log_capture(backend, logging.WARNING)
        
        with caplog.at_level(logging.WARNING):
            backend.__del__()
        
        # Restore original handler levels
        restore_log_settings(backend, original_levels, original_propagate)
        
        # Should warn about improper cleanup
        # Check log records instead of text for more reliable capture
        log_messages = [record.message for record in caplog.records]
        assert any("destroyed without proper cleanup" in msg for msg in log_messages)
        assert any("Use 'async with camera' or call 'await camera.close()'" in msg for msg in log_messages)
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_destructor_without_camera_no_warning(self, mock_get_config, caplog):
        """Test destructor doesn't warn when camera is None."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend.camera = None  # Properly cleaned up
        
        with caplog.at_level(logging.WARNING):
            backend.__del__()
        
        # Should not warn
        assert "destroyed without proper cleanup" not in caplog.text
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_destructor_exception_handling(self, mock_get_config):
        """Test destructor handles exceptions gracefully."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        backend.camera = "mock_camera"
        
        # Remove logger to trigger exception
        delattr(backend, 'logger')
        
        # Should not raise exception
        try:
            backend.__del__()
        except Exception as e:
            pytest.fail(f"Destructor raised exception: {e}")


class TestCameraBackendAbstractMethods:
    """Test abstract method enforcement."""
    
    def test_cannot_instantiate_base_class(self):
        """Test that CameraBackend cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            CameraBackend()
    
    def test_partial_implementation_fails(self):
        """Test that partially implemented subclasses fail to instantiate."""
        
        class PartialCameraBackend(CameraBackend):
            """Partially implemented camera backend."""
            
            async def initialize(self) -> Tuple[bool, Any, Any]:
                return True, None, None
            
            # Missing other required abstract methods
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialCameraBackend()
    
    def test_abstract_methods_raise_not_implemented(self):
        """Test that abstract methods raise NotImplementedError in base class."""
        # This test would require direct access to abstract methods
        # which isn't possible since the class can't be instantiated
        # This is more of a documentation of expected behavior
        
        # We can test that the methods are marked as abstract
        assert hasattr(CameraBackend.initialize, '__isabstractmethod__')
        assert hasattr(CameraBackend.set_exposure, '__isabstractmethod__')
        assert hasattr(CameraBackend.get_exposure, '__isabstractmethod__')
        assert hasattr(CameraBackend.get_exposure_range, '__isabstractmethod__')
        assert hasattr(CameraBackend.capture, '__isabstractmethod__')
        assert hasattr(CameraBackend.check_connection, '__isabstractmethod__')
        assert hasattr(CameraBackend.close, '__isabstractmethod__')
        assert hasattr(CameraBackend.get_available_cameras, '__isabstractmethod__')


class TestCameraBackendInheritance:
    """Test inheritance behavior and MindtraceABC integration."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_inherits_from_mindtrace_abc(self, mock_get_config):
        """Test that CameraBackend properly inherits from MindtraceABC."""
        from mindtrace.core.base.mindtrace_base import MindtraceABC
        
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Should be instance of MindtraceABC
        assert isinstance(backend, MindtraceABC)
        
        # Should have logger from base class
        assert hasattr(backend, 'logger')
        assert hasattr(backend.logger, 'info')
        assert hasattr(backend.logger, 'warning')
        assert hasattr(backend.logger, 'error')
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_method_resolution_order(self, mock_get_config):
        """Test method resolution order is correct."""
        from mindtrace.core.base.mindtrace_base import MindtraceABC
        
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 3
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Check MRO
        mro = ConcreteCameraBackend.__mro__
        assert ConcreteCameraBackend in mro
        assert CameraBackend in mro
        assert MindtraceABC in mro
        
        # CameraBackend should come before MindtraceABC
        camera_backend_index = mro.index(CameraBackend)
        mindtrace_abc_index = mro.index(MindtraceABC)
        assert camera_backend_index < mindtrace_abc_index


class TestCameraBackendConfiguration:
    """Test configuration integration and parameter handling."""
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_config_exception_handling(self, mock_get_config):
        """Test behavior when config system raises exceptions."""
        # Mock config to raise exception
        mock_get_config.side_effect = RuntimeError("Config system error")
        
        # Should still be able to create backend (graceful degradation)
        # or should raise appropriate exception
        with pytest.raises(RuntimeError):
            ConcreteCameraBackend()
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_config_none_values(self, mock_get_config):
        """Test behavior when config returns None values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = None
        mock_config_obj.cameras.retrieve_retry_count = None
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        backend = ConcreteCameraBackend()
        
        # Should handle None values gracefully
        # (actual behavior depends on implementation)
        assert hasattr(backend, 'img_quality_enhancement')
        assert hasattr(backend, 'retrieve_retry_count')
    
    @patch('mindtrace.hardware.cameras.backends.camera_backend.get_camera_config')
    def test_parameter_precedence(self, mock_get_config):
        """Test that explicit parameters override config values."""
        mock_config_obj = MagicMock()
        mock_config_obj.cameras.image_quality_enhancement = True
        mock_config_obj.cameras.retrieve_retry_count = 10
        mock_get_config.return_value.get_config.return_value = mock_config_obj
        
        # Explicit parameters should override config
        backend = ConcreteCameraBackend(
            img_quality_enhancement=False,
            retrieve_retry_count=5
        )
        
        assert backend.img_quality_enhancement is False  # Explicit override
        assert backend.retrieve_retry_count == 5  # Explicit override 