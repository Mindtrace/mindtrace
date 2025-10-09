"""
CameraManagerService - Service-based API for camera management.

This service wraps AsyncCameraManager functionality in a Service-based
architecture with comprehensive MCP tool integration and typed client access.
"""

import os
import time
from datetime import datetime, timezone
from typing import Optional

from mindtrace.hardware.api.cameras.models import (
    # Response models
    ActiveCamerasResponse,
    ActiveStreamsResponse,
    # Requests
    BackendFilterRequest,
    # Data models
    BackendInfo,
    BackendInfoResponse,
    BackendsResponse,
    BandwidthLimitRequest,
    BandwidthSettings,
    BandwidthSettingsResponse,
    BatchCaptureResponse,
    BatchHDRCaptureResponse,
    BatchOperationResponse,
    BatchOperationResult,
    BoolResponse,
    CameraCapabilities,
    CameraCapabilitiesResponse,
    CameraCloseBatchRequest,
    CameraCloseRequest,
    CameraConfiguration,
    CameraConfigurationResponse,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraInfo,
    CameraInfoResponse,
    CameraOpenBatchRequest,
    CameraOpenRequest,
    CameraQueryRequest,
    CameraStatus,
    CameraStatusResponse,
    CaptureBatchRequest,
    CaptureHDRBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    CaptureResponse,
    CaptureResult,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
    ConfigFileOperationResult,
    ConfigFileResponse,
    HDRCaptureResponse,
    HDRCaptureResult,
    ListResponse,
    NetworkDiagnostics,
    NetworkDiagnosticsResponse,
    StreamInfo,
    StreamInfoResponse,
    StreamStartRequest,
    StreamStatus,
    StreamStatusRequest,
    StreamStatusResponse,
    StreamStopRequest,
    SystemDiagnostics,
    SystemDiagnosticsResponse,
)
from mindtrace.hardware.api.cameras.schemas import ALL_SCHEMAS
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.core.exceptions import (
    CameraNotFoundError,
    CameraTimeoutError,
)
from mindtrace.services import Service


class CameraManagerService(Service):
    """
    Camera Management Service.

    Provides comprehensive camera management functionality through a Service-based
    architecture with MCP tool integration and async camera operations.
    """

    def __init__(self, include_mocks: bool = False, **kwargs):
        """Initialize CameraManagerService.

        Args:
            include_mocks: Include mock cameras in discovery
            **kwargs: Additional Service initialization parameters
        """
        super().__init__(
            summary="Camera Management Service",
            description="REST API and MCP tools for comprehensive camera management and control",
            **kwargs,
        )

        self.include_mocks = include_mocks
        self._camera_manager: Optional[AsyncCameraManager] = None
        self._startup_time = time.time()
        self._active_streams: dict = {}  # Track active camera streams

        # Register all endpoints with their schemas
        self._register_endpoints()

    async def _get_camera_manager(self) -> AsyncCameraManager:
        """Get or create camera manager instance."""
        self.logger.debug(f"_get_camera_manager called, current manager: {self._camera_manager}")
        if self._camera_manager is None:
            self.logger.debug("Creating new AsyncCameraManager")
            self._camera_manager = AsyncCameraManager(include_mocks=self.include_mocks)
            self.logger.debug("Calling __aenter__ on camera manager")
            await self._camera_manager.__aenter__()
            self.logger.debug("AsyncCameraManager initialization completed")
        self.logger.debug("Returning camera manager")
        return self._camera_manager

    async def shutdown_cleanup(self):
        """Cleanup camera manager on shutdown."""
        # Stop all active streams
        if hasattr(self, '_active_streams'):
            self._active_streams.clear()
            
        if self._camera_manager is not None:
            try:
                await self._camera_manager.__aexit__(None, None, None)
            except Exception as e:
                self.logger.error(f"Error closing camera manager: {e}")
            finally:
                self._camera_manager = None
        await super().shutdown_cleanup()

    def _register_endpoints(self):
        """Register all service endpoints."""
        # Backend & Discovery
        self.add_endpoint("backends", self.discover_backends, ALL_SCHEMAS["discover_backends"], methods=["GET"], as_tool=True)
        self.add_endpoint("backends/info", self.get_backend_info, ALL_SCHEMAS["get_backend_info"], methods=["GET"], as_tool=True)
        self.add_endpoint("cameras/discover", self.discover_cameras, ALL_SCHEMAS["discover_cameras"], methods=["POST"], as_tool=True)

        # Camera Lifecycle
        self.add_endpoint("cameras/open", self.open_camera, ALL_SCHEMAS["open_camera"], as_tool=True)
        self.add_endpoint("cameras/open/batch", self.open_cameras_batch, ALL_SCHEMAS["open_cameras_batch"], as_tool=True)
        self.add_endpoint("cameras/close", self.close_camera, ALL_SCHEMAS["close_camera"], as_tool=True)
        self.add_endpoint("cameras/close/batch", self.close_cameras_batch, ALL_SCHEMAS["close_cameras_batch"], as_tool=True)
        self.add_endpoint("cameras/close/all", self.close_all_cameras, ALL_SCHEMAS["close_all_cameras"], as_tool=True)
        self.add_endpoint("cameras/active", self.get_active_cameras, ALL_SCHEMAS["get_active_cameras"], methods=["GET"], as_tool=True)

        # Camera Status & Information
        self.add_endpoint("cameras/status", self.get_camera_status, ALL_SCHEMAS["get_camera_status"], as_tool=True)
        self.add_endpoint("cameras/info", self.get_camera_info, ALL_SCHEMAS["get_camera_info"], as_tool=True)
        self.add_endpoint("cameras/capabilities", self.get_camera_capabilities, ALL_SCHEMAS["get_camera_capabilities"], as_tool=True)
        self.add_endpoint(
            "system/diagnostics", self.get_system_diagnostics, ALL_SCHEMAS["get_system_diagnostics"], methods=["GET"], as_tool=True
        )

        # Camera Configuration
        self.add_endpoint("cameras/configure", self.configure_camera, ALL_SCHEMAS["configure_camera"], as_tool=True)
        self.add_endpoint(
            "cameras/configure/batch", self.configure_cameras_batch, ALL_SCHEMAS["configure_cameras_batch"], as_tool=True
        )
        self.add_endpoint(
            "cameras/configuration", self.get_camera_configuration, ALL_SCHEMAS["get_camera_configuration"], as_tool=True
        )
        self.add_endpoint("cameras/config/import", self.import_camera_config, ALL_SCHEMAS["import_camera_config"], as_tool=True)
        self.add_endpoint("cameras/config/export", self.export_camera_config, ALL_SCHEMAS["export_camera_config"], as_tool=True)

        # Image Capture
        self.add_endpoint("cameras/capture", self.capture_image, ALL_SCHEMAS["capture_image"], as_tool=True)
        self.add_endpoint("cameras/capture/batch", self.capture_images_batch, ALL_SCHEMAS["capture_images_batch"], as_tool=True)
        self.add_endpoint("cameras/capture/hdr", self.capture_hdr_image, ALL_SCHEMAS["capture_hdr_image"], as_tool=True)
        self.add_endpoint(
            "cameras/capture/hdr/batch", self.capture_hdr_images_batch, ALL_SCHEMAS["capture_hdr_images_batch"], as_tool=True
        )

        # Streaming (REST API only - not as MCP tools)
        self.add_endpoint("cameras/stream/start", self.start_stream, ALL_SCHEMAS["stream_start"])
        self.add_endpoint("cameras/stream/stop", self.stop_stream, ALL_SCHEMAS["stream_stop"])
        self.add_endpoint("cameras/stream/status", self.get_stream_status, ALL_SCHEMAS["stream_status"])
        self.add_endpoint("cameras/stream/active", self.get_active_streams, ALL_SCHEMAS["get_active_streams"], methods=["GET"])
        self.add_endpoint("cameras/stream/stop/all", self.stop_all_streams, ALL_SCHEMAS["stop_all_streams"], methods=["POST"])
        
        # Video stream endpoints (serve actual video)
        self.add_endpoint("stream/{camera_name}", self.serve_camera_stream, None, methods=["GET"])

        # Network & Bandwidth
        self.add_endpoint(
            "network/bandwidth", self.get_bandwidth_settings, ALL_SCHEMAS["get_bandwidth_settings"], methods=["GET"], as_tool=True
        )
        self.add_endpoint("network/bandwidth/limit", self.set_bandwidth_limit, ALL_SCHEMAS["set_bandwidth_limit"], as_tool=True)
        self.add_endpoint(
            "network/diagnostics", self.get_network_diagnostics, ALL_SCHEMAS["get_network_diagnostics"], methods=["GET"], as_tool=True
        )



    # Backend & Discovery Operations
    async def discover_backends(self) -> BackendsResponse:
        """Discover available camera backends."""
        try:
            manager = await self._get_camera_manager()
            backends = manager.backends()

            return BackendsResponse(success=True, message=f"Found {len(backends)} available backends", data=backends)
        except Exception as e:
            self.logger.error(f"Backend discovery failed: {e}")
            raise

    async def get_backend_info(self) -> BackendInfoResponse:
        """Get detailed information about all backends."""
        try:
            manager = await self._get_camera_manager()
            backend_info = manager.backend_info()

            # Convert to BackendInfo models
            backend_models = {}
            for name, info in backend_info.items():
                backend_models[name] = BackendInfo(
                    name=name,
                    available=info["available"],
                    type=info["type"],
                    sdk_required=info["sdk_required"],
                    description=f"{name} camera backend",
                )

            return BackendInfoResponse(
                success=True, message=f"Retrieved information for {len(backend_models)} backends", data=backend_models
            )
        except Exception as e:
            self.logger.error(f"Backend info retrieval failed: {e}")
            raise

    async def discover_cameras(self, request: BackendFilterRequest) -> ListResponse:
        """Discover available cameras from all or specific backends."""
        try:
            manager = await self._get_camera_manager()
            cameras = manager.discover(backends=request.backend, include_mocks=self.include_mocks)

            return ListResponse(
                success=True,
                message=f"Found {len(cameras)} cameras"
                + (f" from backend '{request.backend}'" if request.backend else " from all backends"),
                data=cameras,
            )
        except Exception as e:
            self.logger.error(f"Camera discovery failed: {e}")
            raise

    # Camera Lifecycle Operations
    async def open_camera(self, request: CameraOpenRequest) -> BoolResponse:
        """Open a single camera with exposure validation."""
        try:
            manager = await self._get_camera_manager()
            await manager.open(request.camera, test_connection=request.test_connection)

            # Check exposure time and warn if too high for streaming
            try:
                camera_proxy = await manager.get_camera(request.camera)
                if camera_proxy:
                    # Try to get exposure time (GenICam cameras)
                    if hasattr(camera_proxy._backend, 'image_acquirer'):
                        ia = camera_proxy._backend.image_acquirer
                        if ia and hasattr(ia, 'remote_device'):
                            node_map = ia.remote_device.node_map
                            if hasattr(node_map, 'ExposureTime'):
                                exposure_us = node_map.ExposureTime.value
                                exposure_ms = exposure_us / 1000.0

                                if exposure_ms > 1000:  # > 1 second
                                    self.logger.warning(
                                        f"Camera '{request.camera}' has high exposure time: {exposure_ms:.0f}ms. "
                                        f"This will cause slow capture (<1 FPS) and streaming timeouts. "
                                        f"Recommended: <100ms for streaming, <500ms for general use."
                                    )
                                elif exposure_ms > 100:  # > 100ms
                                    self.logger.info(
                                        f"Camera '{request.camera}' exposure time: {exposure_ms:.0f}ms. "
                                        f"This may be slow for real-time streaming (< {1000/exposure_ms:.1f} FPS max). "
                                        f"Consider reducing exposure for better streaming performance."
                                    )
            except Exception as e:
                # Don't fail the open operation if exposure check fails
                self.logger.debug(f"Could not check exposure time for '{request.camera}': {e}")

            return BoolResponse(success=True, message=f"Camera '{request.camera}' opened successfully", data=True)
        except Exception as e:
            self.logger.error(f"Failed to open camera '{request.camera}': {e}")
            raise

    async def open_cameras_batch(self, request: CameraOpenBatchRequest) -> BatchOperationResponse:
        """Open multiple cameras in batch."""
        try:
            manager = await self._get_camera_manager()
            opened = await manager.open(request.cameras, test_connection=request.test_connection)

            successful = list(opened.keys())
            failed = [c for c in request.cameras if c not in successful]

            result = BatchOperationResult(
                successful=successful,
                failed=failed,
                results={c: (c in successful) for c in request.cameras},
                successful_count=len(successful),
                failed_count=len(failed),
            )

            return BatchOperationResponse(
                success=len(failed) == 0,
                message=f"Batch open completed: {len(successful)} successful, {len(failed)} failed",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Batch camera opening failed: {e}")
            raise

    async def close_camera(self, request: CameraCloseRequest) -> BoolResponse:
        """Close a specific camera."""
        self.logger.info(f"Starting close_camera for '{request.camera}'")
        try:
            self.logger.debug("Getting camera manager...")
            manager = await self._get_camera_manager()

            self.logger.debug(f"Calling manager.close for camera '{request.camera}'")
            await manager.close(request.camera)
            self.logger.debug(f"Close completed for camera '{request.camera}'")

            return BoolResponse(success=True, message=f"Camera '{request.camera}' closed successfully", data=True)
        except Exception as e:
            self.logger.error(f"Failed to close camera '{request.camera}': {e}")
            raise

    async def close_cameras_batch(self, request: CameraCloseBatchRequest) -> BatchOperationResponse:
        """Close multiple cameras in batch."""
        try:
            manager = await self._get_camera_manager()

            # Close cameras individually to track success/failure
            results = {}
            successful = []
            failed = []

            for camera in request.cameras:
                try:
                    await manager.close(camera)
                    results[camera] = True
                    successful.append(camera)
                except Exception as e:
                    self.logger.warning(f"Failed to close camera '{camera}': {e}")
                    results[camera] = False
                    failed.append(camera)

            result = BatchOperationResult(
                successful=successful,
                failed=failed,
                results=results,
                successful_count=len(successful),
                failed_count=len(failed),
            )

            return BatchOperationResponse(
                success=len(failed) == 0,
                message=f"Batch close completed: {len(successful)} successful, {len(failed)} failed",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Batch camera closing failed: {e}")
            raise

    async def close_all_cameras(self) -> BoolResponse:
        """Close all active cameras."""
        try:
            manager = await self._get_camera_manager()
            active_cameras = manager.active_cameras
            camera_count = len(active_cameras)

            await manager.close()

            return BoolResponse(success=True, message=f"Successfully closed {camera_count} cameras", data=True)
        except Exception as e:
            self.logger.error(f"Failed to close all cameras: {e}")
            raise

    async def get_active_cameras(self) -> ActiveCamerasResponse:
        """Get list of currently active cameras."""
        try:
            manager = await self._get_camera_manager()
            active_cameras = manager.active_cameras

            return ActiveCamerasResponse(
                success=True, message=f"Found {len(active_cameras)} active cameras", data=active_cameras
            )
        except Exception as e:
            self.logger.error(f"Failed to get active cameras: {e}")
            raise

    # Camera Status & Information Operations
    async def get_camera_status(self, request: CameraQueryRequest) -> CameraStatusResponse:
        """Get camera status information."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            # Get camera proxy and check connection
            camera_proxy = await manager.open(request.camera)
            is_connected = await camera_proxy.check_connection()

            status = CameraStatus(
                camera=request.camera,
                connected=is_connected,
                initialized=True,
                backend=request.camera.split(":")[0],
                device_name=request.camera.split(":")[1],
                error_count=0,
            )

            return CameraStatusResponse(
                success=True, message=f"Retrieved status for camera '{request.camera}'", data=status
            )
        except Exception as e:
            self.logger.error(f"Failed to get camera status for '{request.camera}': {e}")
            raise

    async def get_camera_info(self, request: CameraQueryRequest) -> CameraInfoResponse:
        """Get detailed camera information."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)
            sensor_info = await camera_proxy.get_sensor_info()

            # Fix sensor_info to avoid serialization issues with backend object
            safe_sensor_info = {
                "name": sensor_info.get("name"),
                "backend": request.camera.split(":")[0],  # Use string not object
                "device_name": sensor_info.get("device_name"),
                "connected": sensor_info.get("connected"),
            }

            info = CameraInfo(
                name=request.camera,
                backend=request.camera.split(":")[0],
                device_name=request.camera.split(":")[1],
                active=True,
                connected=camera_proxy.is_connected,
                sensor_info=safe_sensor_info,
            )

            return CameraInfoResponse(
                success=True, message=f"Retrieved information for camera '{request.camera}'", data=info
            )
        except Exception as e:
            self.logger.error(f"Failed to get camera info for '{request.camera}': {e}")
            raise

    async def get_camera_capabilities(self, request: CameraQueryRequest) -> CameraCapabilitiesResponse:
        """Get camera capabilities information."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)

            # Get capabilities from camera backend
            try:
                exposure_range = await camera_proxy.get_exposure_range()
                # For OpenCV cameras, explicitly disable exposure control as most don't support it
                if request.camera.startswith("OpenCV:") and exposure_range is not None:
                    # Double-check that exposure control is actually supported
                    if hasattr(camera_proxy.backend, 'is_exposure_control_supported'):
                        if not await camera_proxy.backend.is_exposure_control_supported():
                            exposure_range = None
            except Exception:
                exposure_range = None

            try:
                gain_range = await camera_proxy.get_gain_range()
            except Exception:
                gain_range = None

            try:
                pixel_formats = await camera_proxy.get_available_pixel_formats()
            except Exception:
                pixel_formats = None

            try:
                white_balance_modes = await camera_proxy.get_available_white_balance_modes()
            except Exception:
                white_balance_modes = None

            # Get trigger modes (backend-specific implementation)
            try:
                backend = camera_proxy.backend
                if hasattr(backend, 'get_trigger_modes'):
                    trigger_modes = await backend.get_trigger_modes()
                else:
                    # Default trigger modes for most cameras
                    trigger_modes = ["continuous", "triggered"]
            except Exception:
                trigger_modes = None

            try:
                width_range = await camera_proxy.backend.get_width_range()
            except Exception:
                width_range = None

            try:
                height_range = await camera_proxy.backend.get_height_range()
            except Exception:
                height_range = None

            # Network parameters (Basler-specific)
            try:
                if hasattr(camera_proxy.backend, 'get_bandwidth_limit_range'):
                    bandwidth_limit_range = await camera_proxy.backend.get_bandwidth_limit_range()
                else:
                    bandwidth_limit_range = None
            except Exception:
                bandwidth_limit_range = None

            try:
                if hasattr(camera_proxy.backend, 'get_packet_size_range'):
                    packet_size_range = await camera_proxy.backend.get_packet_size_range()
                else:
                    packet_size_range = None
            except Exception:
                packet_size_range = None

            try:
                if hasattr(camera_proxy.backend, 'get_inter_packet_delay_range'):
                    inter_packet_delay_range = await camera_proxy.backend.get_inter_packet_delay_range()
                else:
                    inter_packet_delay_range = None
            except Exception:
                inter_packet_delay_range = None

            capabilities = CameraCapabilities(
                exposure_range=exposure_range,
                gain_range=gain_range,
                pixel_formats=pixel_formats,
                white_balance_modes=white_balance_modes,
                trigger_modes=trigger_modes,
                width_range=width_range,
                height_range=height_range,
                bandwidth_limit_range=bandwidth_limit_range,
                packet_size_range=packet_size_range,
                inter_packet_delay_range=inter_packet_delay_range,
                supports_roi=True,  # Most cameras support ROI
                supports_trigger=True,  # Most cameras support trigger
                supports_hdr=True,  # Our implementation supports HDR
            )

            return CameraCapabilitiesResponse(
                success=True, message=f"Retrieved capabilities for camera '{request.camera}'", data=capabilities
            )
        except Exception as e:
            self.logger.error(f"Failed to get camera capabilities for '{request.camera}': {e}")
            raise

    # Camera Configuration Operations
    async def configure_camera(self, request: CameraConfigureRequest) -> BoolResponse:
        """Configure camera parameters."""
        self.logger.info(f"Starting configure_camera for '{request.camera}' with properties: {request.properties}")
        try:
            self.logger.debug("Getting camera manager...")
            manager = await self._get_camera_manager()

            # Check if camera is active
            self.logger.debug(
                f"Checking if camera '{request.camera}' is in active cameras: {list(manager.active_cameras)}"
            )
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            self.logger.debug(f"Opening camera proxy for '{request.camera}'...")
            camera_proxy = await manager.open(request.camera)

            self.logger.debug(f"Calling configure on camera proxy with properties: {request.properties}")
            success = await camera_proxy.configure(**request.properties)
            self.logger.debug(f"Configure completed with success: {success}")

            # Handle None return value (convert to False)
            if success is None:
                success = False
                
            return BoolResponse(
                success=success,
                message=f"Camera '{request.camera}' configured successfully"
                if success
                else f"Configuration failed for '{request.camera}'",
                data=success,
            )
        except CameraNotFoundError as e:
            # Handle camera not found errors gracefully
            self.logger.warning(f"Camera not found: {e}")
            return BoolResponse(
                success=False,
                message=str(e),
                data=False
            )
        except Exception as e:
            self.logger.error(f"Failed to configure camera '{request.camera}': {e}")
            # Import the exception types
            from mindtrace.hardware.core.exceptions import CameraConfigurationError, HardwareOperationError
            
            # Handle configuration errors gracefully
            if isinstance(e, (CameraConfigurationError, HardwareOperationError, TypeError)):
                # Return a failure response with the error message instead of raising
                return BoolResponse(
                    success=False,
                    message=str(e),
                    data=False
                )
            # For other exceptions, still raise them
            raise

    async def configure_cameras_batch(self, request: CameraConfigureBatchRequest) -> BatchOperationResponse:
        """Configure multiple cameras in batch."""
        try:
            manager = await self._get_camera_manager()
            results = await manager.batch_configure(request.configurations)

            successful = [name for name, success in results.items() if success]
            failed = [name for name, success in results.items() if not success]

            result = BatchOperationResult(
                successful=successful,
                failed=failed,
                results=results,
                successful_count=len(successful),
                failed_count=len(failed),
            )

            return BatchOperationResponse(
                success=len(failed) == 0,
                message=f"Batch configure completed: {len(successful)} successful, {len(failed)} failed",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Batch camera configuration failed: {e}")
            raise

    async def get_camera_configuration(self, request: CameraQueryRequest) -> CameraConfigurationResponse:
        """Get current camera configuration."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)

            # Get current configuration
            try:
                roi_data = await camera_proxy.get_roi()
                roi_tuple = (
                    roi_data.get("x", 0),
                    roi_data.get("y", 0),
                    roi_data.get("width", 0),
                    roi_data.get("height", 0),
                )
            except Exception:
                roi_tuple = None

            # Get individual configuration parameters with error handling
            try:
                exposure_time = await camera_proxy.get_exposure()
            except Exception:
                exposure_time = None

            try:
                gain = await camera_proxy.get_gain()
            except Exception:
                gain = None

            try:
                trigger_mode = await camera_proxy.get_trigger_mode()
            except Exception:
                trigger_mode = None

            try:
                pixel_format = await camera_proxy.get_pixel_format()
            except Exception:
                pixel_format = None

            try:
                white_balance = await camera_proxy.get_white_balance()
            except Exception:
                white_balance = None

            try:
                image_enhancement = await camera_proxy.get_image_enhancement()
            except Exception:
                image_enhancement = None

            config = CameraConfiguration(
                exposure_time=exposure_time,
                gain=gain,
                roi=roi_tuple,
                trigger_mode=trigger_mode,
                pixel_format=pixel_format,
                white_balance=white_balance,
                image_enhancement=image_enhancement,
            )

            return CameraConfigurationResponse(
                success=True, message=f"Retrieved configuration for camera '{request.camera}'", data=config
            )
        except Exception as e:
            self.logger.error(f"Failed to get camera configuration for '{request.camera}': {e}")
            raise

    async def import_camera_config(self, request: ConfigFileImportRequest) -> ConfigFileResponse:
        """Import camera configuration from file."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)
            success = await camera_proxy.load_config(request.config_path)

            result = ConfigFileOperationResult(file_path=request.config_path, operation="import", success=success)

            return ConfigFileResponse(
                success=success,
                message=f"Configuration imported for camera '{request.camera}'"
                if success
                else f"Import failed for '{request.camera}'",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Failed to import config for camera '{request.camera}': {e}")
            raise

    async def export_camera_config(self, request: ConfigFileExportRequest) -> ConfigFileResponse:
        """Export camera configuration to file."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)
            success = await camera_proxy.save_config(request.config_path)

            result = ConfigFileOperationResult(file_path=request.config_path, operation="export", success=success)

            return ConfigFileResponse(
                success=success,
                message=f"Configuration exported for camera '{request.camera}'"
                if success
                else f"Export failed for '{request.camera}'",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Failed to export config for camera '{request.camera}': {e}")
            raise

    # Image Capture Operations
    async def capture_image(self, request: CaptureImageRequest) -> CaptureResponse:
        """Capture a single image with timeout protection."""
        import asyncio

        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)

            # Capture with 15 second timeout (allows for some overhead but prevents indefinite hang)
            capture_timeout = 15.0

            try:
                await asyncio.wait_for(
                    camera_proxy.capture(
                        save_path=request.save_path, upload_to_gcs=request.upload_to_gcs, output_format=request.output_format
                    ),
                    timeout=capture_timeout
                )

                result = CaptureResult(success=True, image_path=request.save_path, capture_time=datetime.now(timezone.utc))
                return CaptureResponse(success=True, message=f"Image captured from camera '{request.camera}'", data=result)

            except asyncio.TimeoutError:
                error_msg = (
                    f"Capture timeout after {capture_timeout}s for camera '{request.camera}'. "
                    f"Camera exposure time may be too high. Configure with lower exposure time (<1000ms recommended)."
                )
                self.logger.error(error_msg)
                raise CameraTimeoutError(error_msg)

        except CameraTimeoutError as e:
            # Return timeout error as failed response with detailed message
            self.logger.error(f"Capture timeout: {e}")
            result = CaptureResult(success=False, image_path=None, capture_time=datetime.now(timezone.utc), error=str(e))
            return CaptureResponse(success=False, message=str(e), data=result)
        except CameraNotFoundError as e:
            # Return not found error as failed response
            self.logger.warning(f"Camera not found: {e}")
            result = CaptureResult(success=False, image_path=None, capture_time=datetime.now(timezone.utc), error=str(e))
            return CaptureResponse(success=False, message=str(e), data=result)
        except Exception as e:
            self.logger.error(f"Failed to capture image from '{request.camera}': {e}")
            result = CaptureResult(success=False, image_path=None, capture_time=datetime.now(timezone.utc), error=str(e))
            return CaptureResponse(success=False, message=f"Capture failed: {str(e)}", data=result)

    async def capture_images_batch(self, request: CaptureBatchRequest) -> BatchCaptureResponse:
        """Capture images from multiple cameras."""
        try:
            manager = await self._get_camera_manager()
            results = await manager.batch_capture(
                request.cameras, upload_to_gcs=request.upload_to_gcs, output_format=request.output_format
            )

            capture_results = {}
            successful_count = 0

            for camera, image in results.items():
                if image is not None:
                    capture_results[camera] = CaptureResult(success=True, capture_time=datetime.now(timezone.utc))
                    successful_count += 1
                else:
                    capture_results[camera] = CaptureResult(success=False, capture_time=datetime.now(timezone.utc))

            return BatchCaptureResponse(
                success=successful_count > 0,
                message=f"Batch capture completed: {successful_count} successful, {len(results) - successful_count} failed",
                data=capture_results,
                successful_count=successful_count,
                failed_count=len(results) - successful_count,
            )
        except Exception as e:
            self.logger.error(f"Batch image capture failed: {e}")
            raise

    async def capture_hdr_image(self, request: CaptureHDRRequest) -> HDRCaptureResponse:
        """Capture HDR image sequence."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)
            hdr_result = await camera_proxy.capture_hdr(
                save_path_pattern=request.save_path_pattern,
                exposure_levels=request.exposure_levels,
                exposure_multiplier=request.exposure_multiplier,
                return_images=request.return_images,
                upload_to_gcs=request.upload_to_gcs,
                output_format=request.output_format,
            )

            result = HDRCaptureResult(
                success=hdr_result["success"],
                images=hdr_result["images"],
                image_paths=hdr_result["image_paths"],
                gcs_urls=hdr_result["gcs_urls"],
                exposure_levels=hdr_result["exposure_levels"],
                capture_time=datetime.now(timezone.utc),
                successful_captures=hdr_result["successful_captures"],
            )

            return HDRCaptureResponse(
                success=True, message=f"HDR image captured from camera '{request.camera}'", data=result
            )
        except Exception as e:
            self.logger.error(f"Failed to capture HDR image from '{request.camera}': {e}")
            raise

    async def capture_hdr_images_batch(self, request: CaptureHDRBatchRequest) -> BatchHDRCaptureResponse:
        """Capture HDR images from multiple cameras."""
        try:
            manager = await self._get_camera_manager()
            results = await manager.batch_capture_hdr(
                request.cameras,
                save_path_pattern=request.save_path_pattern,
                exposure_levels=request.exposure_levels,
                exposure_multiplier=request.exposure_multiplier,
                return_images=request.return_images,
                upload_to_gcs=request.upload_to_gcs,
                output_format=request.output_format,
            )

            hdr_results = {}
            successful_count = 0

            for camera, hdr_data in results.items():
                if hdr_data and isinstance(hdr_data, dict):
                    hdr_results[camera] = HDRCaptureResult(
                        success=hdr_data.get("success", True),
                        images=hdr_data.get("images"),
                        image_paths=hdr_data.get("image_paths"),
                        gcs_urls=hdr_data.get("gcs_urls"),
                        exposure_levels=hdr_data.get("exposure_levels", []),
                        capture_time=datetime.now(timezone.utc),
                        successful_captures=hdr_data.get("successful_captures", 0),
                    )
                    successful_count += 1
                else:
                    hdr_results[camera] = HDRCaptureResult(
                        success=False,
                        images=None,
                        image_paths=None,
                        gcs_urls=None,
                        exposure_levels=[],
                        capture_time=datetime.now(timezone.utc),
                        successful_captures=0,
                    )

            return BatchHDRCaptureResponse(
                success=successful_count > 0,
                message=f"Batch HDR capture completed: {successful_count} successful, {len(results) - successful_count} failed",
                data=hdr_results,
                successful_count=successful_count,
                failed_count=len(results) - successful_count,
            )
        except Exception as e:
            self.logger.error(f"Batch HDR image capture failed: {e}")
            raise

    # Network & Bandwidth Operations
    async def get_bandwidth_settings(self) -> BandwidthSettingsResponse:
        """Get current bandwidth settings."""
        try:
            manager = await self._get_camera_manager()

            settings = BandwidthSettings(
                max_concurrent_captures=manager.max_concurrent_captures,
                current_active_captures=len(manager.active_cameras),
                available_slots=manager.max_concurrent_captures - len(manager.active_cameras),
                recommended_limit=2,  # Conservative default
            )

            return BandwidthSettingsResponse(
                success=True, message="Bandwidth settings retrieved successfully", data=settings
            )
        except Exception as e:
            self.logger.error(f"Failed to get bandwidth settings: {e}")
            raise

    async def set_bandwidth_limit(self, request: BandwidthLimitRequest) -> BoolResponse:
        """Set maximum concurrent capture limit."""
        try:
            manager = await self._get_camera_manager()
            manager.max_concurrent_captures = request.max_concurrent_captures

            return BoolResponse(
                success=True, message=f"Bandwidth limit set to {request.max_concurrent_captures}", data=True
            )
        except Exception as e:
            self.logger.error(f"Failed to set bandwidth limit: {e}")
            raise

    async def get_network_diagnostics(self) -> NetworkDiagnosticsResponse:
        """Get network diagnostics information."""
        try:
            manager = await self._get_camera_manager()

            # Count GigE cameras (Basler cameras are typically GigE)
            gige_count = len([cam for cam in manager.active_cameras if "Basler" in cam])

            diagnostics = NetworkDiagnostics(
                gige_cameras_count=gige_count,
                total_bandwidth_usage=0.0,  # Would need real calculation
                jumbo_frames_enabled=True,  # From config
                multicast_enabled=True,  # From config
            )

            return NetworkDiagnosticsResponse(
                success=True, message="Network diagnostics retrieved successfully", data=diagnostics
            )
        except Exception as e:
            self.logger.error(f"Failed to get network diagnostics: {e}")
            raise

    # Streaming Operations
    async def start_stream(self, request: StreamStartRequest) -> StreamInfoResponse:
        """Start camera stream with resilient state management."""
        try:
            manager = await self._get_camera_manager()

            # More resilient camera check - try to initialize if not active
            if request.camera not in manager.active_cameras:
                self.logger.warning(f"Camera '{request.camera}' not in active cameras, attempting to initialize")
                try:
                    # Try to initialize the camera first
                    camera_proxy = await manager.open(request.camera)
                    self.logger.info(f"Successfully initialized camera '{request.camera}' for streaming")
                except Exception as init_error:
                    self.logger.error(f"Failed to initialize camera '{request.camera}': {init_error}")
                    raise CameraNotFoundError(f"Camera '{request.camera}' is not available and could not be initialized")
            else:
                camera_proxy = await manager.open(request.camera)
            
            # Start streaming - return the actual stream URL
            # Use the same host and port as the API service from environment variables
            api_host = os.getenv('CAMERA_API_HOST', 'localhost')
            api_port = os.getenv('CAMERA_API_PORT', '8002')
            stream_url = f"http://{api_host}:{api_port}/stream/{request.camera.replace(':', '_')}"
            
            # Track this stream as active (always update, even if already exists)
            self._active_streams[request.camera] = {
                "stream_url": stream_url,
                "start_time": datetime.now(timezone.utc),
                "camera_proxy": camera_proxy,
                "quality": request.quality,
                "fps": request.fps
            }
            
            stream_info = StreamInfo(
                camera=request.camera,
                streaming=True,
                stream_url=stream_url,
                start_time=datetime.now(timezone.utc)
            )

            return StreamInfoResponse(
                success=True, 
                message=f"Stream started for camera '{request.camera}'", 
                data=stream_info
            )
        except CameraNotFoundError:
            # Re-raise camera not found errors
            raise
        except Exception as e:
            self.logger.error(f"Failed to start stream for '{request.camera}': {e}")
            # Return a more graceful error response instead of raising
            return StreamInfoResponse(
                success=False,
                message=f"Failed to start stream for '{request.camera}': {str(e)}",
                data=None
            )

    async def stop_stream(self, request: StreamStopRequest) -> BoolResponse:
        """Stop camera stream with resilient state management."""
        try:
            # Remove from active streams regardless of camera state
            was_streaming = request.camera in self._active_streams
            if was_streaming:
                del self._active_streams[request.camera]
                self.logger.info(f"Removed camera '{request.camera}' from active streams")
            
            # Don't require camera to be initialized for stopping streams
            # The actual video streaming endpoint doesn't depend on _active_streams anyway
            message = f"Stream stopped for camera '{request.camera}'"
            if not was_streaming:
                message = f"Stream was not active for camera '{request.camera}' (already stopped)"
            
            return BoolResponse(
                success=True, 
                message=message, 
                data=True
            )
        except Exception as e:
            self.logger.warning(f"Exception during stop_stream for '{request.camera}': {e}")
            # Always succeed for stop operations to prevent UI blocking
            # The worst case is we don't update our tracking dict, but streaming still works
            return BoolResponse(
                success=True, 
                message=f"Stream stop attempted for '{request.camera}': {str(e)}", 
                data=True
            )

    async def get_stream_status(self, request: StreamStatusRequest) -> StreamStatusResponse:
        """Get camera stream status with resilient state management."""
        try:
            manager = await self._get_camera_manager()

            # More resilient camera connection check
            is_connected = False
            try:
                if request.camera in manager.active_cameras:
                    camera_proxy = await manager.open(request.camera)
                    is_connected = await camera_proxy.check_connection()
                else:
                    self.logger.warning(f"Camera '{request.camera}' not in active cameras for status check")
            except Exception as conn_error:
                self.logger.warning(f"Could not check connection for '{request.camera}': {conn_error}")
                is_connected = False
            
            # Check if camera is actively streaming (from our tracking)
            is_streaming = request.camera in self._active_streams
            stream_url = None
            uptime_seconds = 0.0
            
            if is_streaming:
                stream_info = self._active_streams[request.camera]
                stream_url = stream_info["stream_url"]
                uptime_seconds = (datetime.now(timezone.utc) - stream_info["start_time"]).total_seconds()
            
            stream_status = StreamStatus(
                camera=request.camera,
                streaming=is_streaming,
                connected=is_connected,
                stream_url=stream_url,
                uptime_seconds=uptime_seconds
            )

            return StreamStatusResponse(
                success=True, 
                message=f"Retrieved stream status for camera '{request.camera}'", 
                data=stream_status
            )
        except Exception as e:
            self.logger.error(f"Failed to get stream status for '{request.camera}': {e}")
            raise

    async def get_active_streams(self) -> ActiveStreamsResponse:
        """Get list of cameras with active streams."""
        try:
            manager = await self._get_camera_manager()
            
            # Return list of cameras with active streams
            active_streams = list(self._active_streams.keys())

            return ActiveStreamsResponse(
                success=True, 
                message=f"Found {len(active_streams)} active streams", 
                data=active_streams
            )
        except Exception as e:
            self.logger.error(f"Failed to get active streams: {e}")
            raise

    async def stop_all_streams(self) -> BoolResponse:
        """Stop all active camera streams."""
        try:
            manager = await self._get_camera_manager()
            
            # Stop all active streams
            stopped_count = len(self._active_streams)
            self._active_streams.clear()
            
            return BoolResponse(
                success=True, 
                message=f"Stopped {stopped_count} active streams successfully", 
                data=True
            )
        except Exception as e:
            self.logger.error(f"Failed to stop all streams: {e}")
            raise

    async def serve_camera_stream(self, camera_name: str):
        """Serve MJPEG video stream for a specific camera."""
        try:
            manager = await self._get_camera_manager()
            
            # Replace first underscore back to colon for camera name (Backend_device → Backend:device)
            actual_camera_name = camera_name.replace('_', ':', 1)
            
            # Check if camera is active
            if actual_camera_name not in manager.active_cameras:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail=f"Camera '{actual_camera_name}' is not initialized")
            
            # Don't check _active_streams since it's not shared across workers
            # Just serve the stream if the camera is initialized
            # The frontend will control when to show/hide the stream
            self.logger.info(f"Serving stream for camera '{actual_camera_name}'")

            camera_proxy = await manager.open(actual_camera_name)
            
            # Check if camera is connected
            is_connected = await camera_proxy.check_connection()
            if not is_connected:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail=f"Camera '{actual_camera_name}' is not connected")
            
            # Create MJPEG streaming response
            from fastapi.responses import StreamingResponse
            import asyncio
            import time
            
            async def generate_mjpeg_stream():
                """Generate MJPEG stream frames."""
                import cv2
                import numpy as np
                boundary = "frame"
                
                # Get dynamic streaming parameters
                stream_info = self._active_streams.get(actual_camera_name, {})
                quality = stream_info.get("quality", 85)
                fps = stream_info.get("fps", 30)
                frame_delay = 1.0 / fps
                
                self.logger.info(f"Starting stream for '{actual_camera_name}' with quality={quality}, fps={fps}")
                
                # Track consecutive timeouts for early termination
                consecutive_timeouts = 0
                max_consecutive_timeouts = 3
                capture_timeout = 10.0  # 10 second timeout per frame

                while True:
                    try:
                        # Capture frame from camera as numpy array with timeout protection
                        frame_np = await asyncio.wait_for(
                            camera_proxy.capture(output_format="numpy"),
                            timeout=capture_timeout
                        )

                        # Reset timeout counter on successful capture
                        consecutive_timeouts = 0

                        if frame_np is not None:
                            # Convert numpy array to JPEG bytes
                            # Ensure it's uint8 and RGB/BGR
                            if frame_np.dtype != np.uint8:
                                frame_np = (frame_np * 255).astype(np.uint8)
                            
                            # Convert RGB to BGR if needed (OpenCV expects BGR)
                            if len(frame_np.shape) == 3 and frame_np.shape[2] == 3:
                                # Assuming RGB input, convert to BGR for cv2
                                frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
                            else:
                                frame_bgr = frame_np
                            
                            # Encode as JPEG with dynamic quality
                            success, jpeg_data = cv2.imencode('.jpg', frame_bgr, 
                                                             [cv2.IMWRITE_JPEG_QUALITY, quality])
                            
                            if success:
                                # Create MJPEG frame (Poseidon format)
                                frame_data = jpeg_data.tobytes()
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                        
                        # Control frame rate with dynamic FPS
                        await asyncio.sleep(frame_delay)

                    except asyncio.TimeoutError:
                        consecutive_timeouts += 1
                        self.logger.warning(
                            f"Frame capture timeout ({consecutive_timeouts}/{max_consecutive_timeouts}) "
                            f"for {actual_camera_name} - capture took >{capture_timeout}s. "
                            f"Camera may have high exposure time configured."
                        )

                        if consecutive_timeouts >= max_consecutive_timeouts:
                            self.logger.error(
                                f"Stream terminated for '{actual_camera_name}' after {max_consecutive_timeouts} "
                                f"consecutive timeouts. Camera exposure time may be too high (>10s). "
                                f"Configure camera with lower exposure time for streaming."
                            )
                            # Send error message as final frame
                            error_msg = (
                                f"Stream terminated: Camera '{actual_camera_name}' capture timeout.\n"
                                f"Exposure time may be too high. Configure camera with exposure <1000ms for streaming."
                            )
                            yield (b'--frame\r\n'
                                   b'Content-Type: text/plain\r\n\r\n' + error_msg.encode() + b'\r\n')
                            break

                        # Wait before retry
                        await asyncio.sleep(1.0)
                        continue

                    except Exception as e:
                        self.logger.warning(f"Frame capture error for {actual_camera_name}: {e}")
                        # Check if camera is still active, if not, stop streaming
                        if actual_camera_name not in manager.active_cameras:
                            self.logger.info(f"Camera '{actual_camera_name}' no longer active, stopping stream")
                            break
                        # Send error frame or continue
                        await asyncio.sleep(0.1)
                        continue
            
            return StreamingResponse(
                generate_mjpeg_stream(),
                media_type=f"multipart/x-mixed-replace; boundary=frame",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to serve stream for '{camera_name}': {e}")
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=f"Stream error: {str(e)}")

    # Add remaining method stubs...
    async def get_system_diagnostics(self) -> SystemDiagnosticsResponse:
        """Get system diagnostics information."""
        try:
            manager = await self._get_camera_manager()
            diagnostics_data = manager.diagnostics()

            # Add uptime calculation
            uptime_seconds = time.time() - self._startup_time

            diagnostics = SystemDiagnostics(
                active_cameras=diagnostics_data["active_cameras"],
                max_concurrent_captures=diagnostics_data["max_concurrent_captures"],
                gige_cameras=diagnostics_data["gige_cameras"],
                bandwidth_management_enabled=diagnostics_data["bandwidth_management_enabled"],
                recommended_settings=diagnostics_data["recommended_settings"],
                backend_status={backend: True for backend in manager.backends()},
                uptime_seconds=uptime_seconds,
            )

            return SystemDiagnosticsResponse(
                success=True, message="System diagnostics retrieved successfully", data=diagnostics
            )
        except Exception as e:
            self.logger.error(f"Failed to get system diagnostics: {e}")
            raise
