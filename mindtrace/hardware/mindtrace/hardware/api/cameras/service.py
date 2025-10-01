"""
CameraManagerService - Service-based API for camera management.

This service wraps AsyncCameraManager functionality in a Service-based
architecture with comprehensive MCP tool integration and typed client access.
"""

import time
from datetime import datetime
from typing import Optional

from mindtrace.hardware.api.cameras.models import (
    # Response models
    ActiveCamerasResponse,
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
    SystemDiagnostics,
    SystemDiagnosticsResponse,
)
from mindtrace.hardware.api.cameras.schemas import ALL_SCHEMAS
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.core.exceptions import (
    CameraNotFoundError,
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

        # Register all endpoints with their schemas
        self._register_endpoints()

        # Register MCP tools for essential operations
        self._register_mcp_tools()

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
        self.add_endpoint("backends", self.discover_backends, ALL_SCHEMAS["discover_backends"], methods=["GET"])
        self.add_endpoint("backends/info", self.get_backend_info, ALL_SCHEMAS["get_backend_info"], methods=["GET"])
        self.add_endpoint("cameras/discover", self.discover_cameras, ALL_SCHEMAS["discover_cameras"], methods=["POST"])

        # Camera Lifecycle
        self.add_endpoint("cameras/open", self.open_camera, ALL_SCHEMAS["open_camera"])
        self.add_endpoint("cameras/open/batch", self.open_cameras_batch, ALL_SCHEMAS["open_cameras_batch"])
        self.add_endpoint("cameras/close", self.close_camera, ALL_SCHEMAS["close_camera"])
        self.add_endpoint("cameras/close/batch", self.close_cameras_batch, ALL_SCHEMAS["close_cameras_batch"])
        self.add_endpoint("cameras/close/all", self.close_all_cameras, ALL_SCHEMAS["close_all_cameras"])
        self.add_endpoint("cameras/active", self.get_active_cameras, ALL_SCHEMAS["get_active_cameras"], methods=["GET"])

        # Camera Status & Information
        self.add_endpoint("cameras/status", self.get_camera_status, ALL_SCHEMAS["get_camera_status"])
        self.add_endpoint("cameras/info", self.get_camera_info, ALL_SCHEMAS["get_camera_info"])
        self.add_endpoint("cameras/capabilities", self.get_camera_capabilities, ALL_SCHEMAS["get_camera_capabilities"])
        self.add_endpoint(
            "system/diagnostics", self.get_system_diagnostics, ALL_SCHEMAS["get_system_diagnostics"], methods=["GET"]
        )

        # Camera Configuration
        self.add_endpoint("cameras/configure", self.configure_camera, ALL_SCHEMAS["configure_camera"])
        self.add_endpoint(
            "cameras/configure/batch", self.configure_cameras_batch, ALL_SCHEMAS["configure_cameras_batch"]
        )
        self.add_endpoint(
            "cameras/configuration", self.get_camera_configuration, ALL_SCHEMAS["get_camera_configuration"]
        )
        self.add_endpoint("cameras/config/import", self.import_camera_config, ALL_SCHEMAS["import_camera_config"])
        self.add_endpoint("cameras/config/export", self.export_camera_config, ALL_SCHEMAS["export_camera_config"])

        # Image Capture
        self.add_endpoint("cameras/capture", self.capture_image, ALL_SCHEMAS["capture_image"])
        self.add_endpoint("cameras/capture/batch", self.capture_images_batch, ALL_SCHEMAS["capture_images_batch"])
        self.add_endpoint("cameras/capture/hdr", self.capture_hdr_image, ALL_SCHEMAS["capture_hdr_image"])
        self.add_endpoint(
            "cameras/capture/hdr/batch", self.capture_hdr_images_batch, ALL_SCHEMAS["capture_hdr_images_batch"]
        )

        # Network & Bandwidth
        self.add_endpoint(
            "network/bandwidth", self.get_bandwidth_settings, ALL_SCHEMAS["get_bandwidth_settings"], methods=["GET"]
        )
        self.add_endpoint("network/bandwidth/limit", self.set_bandwidth_limit, ALL_SCHEMAS["set_bandwidth_limit"])
        self.add_endpoint(
            "network/diagnostics", self.get_network_diagnostics, ALL_SCHEMAS["get_network_diagnostics"], methods=["GET"]
        )

    def _register_mcp_tools(self):
        """Register essential MCP tools."""
        # Essential camera operations
        self.add_endpoint(
            "cameras/discover", self.discover_cameras, ALL_SCHEMAS["discover_cameras"], methods=["POST"], as_tool=True
        )
        self.add_endpoint("cameras/open", self.open_camera, ALL_SCHEMAS["open_camera"], as_tool=True)
        self.add_endpoint("cameras/close", self.close_camera, ALL_SCHEMAS["close_camera"], as_tool=True)
        self.add_endpoint("cameras/close/all", self.close_all_cameras, ALL_SCHEMAS["close_all_cameras"], as_tool=True)
        self.add_endpoint(
            "cameras/active", self.get_active_cameras, ALL_SCHEMAS["get_active_cameras"], methods=["GET"], as_tool=True
        )

        # Core capture operations
        self.add_endpoint("cameras/capture", self.capture_image, ALL_SCHEMAS["capture_image"], as_tool=True)
        self.add_endpoint(
            "cameras/capture/batch", self.capture_images_batch, ALL_SCHEMAS["capture_images_batch"], as_tool=True
        )
        self.add_endpoint("cameras/capture/hdr", self.capture_hdr_image, ALL_SCHEMAS["capture_hdr_image"], as_tool=True)

        # Configuration operations
        self.add_endpoint("cameras/configure", self.configure_camera, ALL_SCHEMAS["configure_camera"], as_tool=True)
        self.add_endpoint(
            "cameras/configuration",
            self.get_camera_configuration,
            ALL_SCHEMAS["get_camera_configuration"],
            as_tool=True,
        )
        self.add_endpoint("cameras/status", self.get_camera_status, ALL_SCHEMAS["get_camera_status"], as_tool=True)

        # System operations
        self.add_endpoint(
            "system/diagnostics",
            self.get_system_diagnostics,
            ALL_SCHEMAS["get_system_diagnostics"],
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint(
            "network/bandwidth/limit", self.set_bandwidth_limit, ALL_SCHEMAS["set_bandwidth_limit"], as_tool=True
        )

        # Configuration persistence
        self.add_endpoint(
            "cameras/config/import", self.import_camera_config, ALL_SCHEMAS["import_camera_config"], as_tool=True
        )
        self.add_endpoint(
            "cameras/config/export", self.export_camera_config, ALL_SCHEMAS["export_camera_config"], as_tool=True
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
        """Open a single camera."""
        try:
            manager = await self._get_camera_manager()
            await manager.open(request.camera, test_connection=request.test_connection)

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

            capabilities = CameraCapabilities(
                exposure_range=exposure_range,
                gain_range=gain_range,
                pixel_formats=pixel_formats,
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

            return BoolResponse(
                success=success,
                message=f"Camera '{request.camera}' configured successfully"
                if success
                else f"Configuration failed for '{request.camera}'",
                data=success,
            )
        except Exception as e:
            self.logger.error(f"Failed to configure camera '{request.camera}': {e}")
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

            config = CameraConfiguration(
                exposure=await camera_proxy.get_exposure(),
                gain=await camera_proxy.get_gain(),
                roi=roi_tuple,
                trigger_mode=await camera_proxy.get_trigger_mode(),
                pixel_format=await camera_proxy.get_pixel_format(),
                white_balance=await camera_proxy.get_white_balance(),
                image_enhancement=await camera_proxy.get_image_enhancement(),
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
        """Capture a single image."""
        try:
            manager = await self._get_camera_manager()

            # Check if camera is active
            if request.camera not in manager.active_cameras:
                raise CameraNotFoundError(f"Camera '{request.camera}' is not initialized")

            camera_proxy = await manager.open(request.camera)
            await camera_proxy.capture(
                save_path=request.save_path, upload_to_gcs=request.upload_to_gcs, output_format=request.output_format
            )

            result = CaptureResult(success=True, image_path=request.save_path, capture_time=datetime.utcnow())

            return CaptureResponse(success=True, message=f"Image captured from camera '{request.camera}'", data=result)
        except Exception as e:
            self.logger.error(f"Failed to capture image from '{request.camera}': {e}")
            raise

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
                    capture_results[camera] = CaptureResult(success=True, capture_time=datetime.utcnow())
                    successful_count += 1
                else:
                    capture_results[camera] = CaptureResult(success=False, capture_time=datetime.utcnow())

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
                capture_time=datetime.utcnow(),
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
                        capture_time=datetime.utcnow(),
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
                        capture_time=datetime.utcnow(),
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
