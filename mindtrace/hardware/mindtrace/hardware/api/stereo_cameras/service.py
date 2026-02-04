"""
StereoCameraService - Service-based API for stereo camera management.

This service provides comprehensive REST API and MCP tools for managing
Basler Stereo ace cameras with multi-component capture (intensity, disparity, depth).
"""

import time
from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from mindtrace.hardware.api.stereo_cameras.models import (
    # Responses
    ActiveStereoCamerasResponse,
    # Requests
    BackendFilterRequest,
    BackendInfo,
    BackendInfoResponse,
    BackendsResponse,
    BatchOperationResponse,
    BatchOperationResult,
    BoolResponse,
    ListResponse,
    PointCloudBatchResponse,
    PointCloudBatchResult,
    PointCloudCaptureBatchRequest,
    PointCloudCaptureRequest,
    PointCloudResponse,
    PointCloudResult,
    StereoCameraCloseBatchRequest,
    StereoCameraCloseRequest,
    StereoCameraConfiguration,
    StereoCameraConfigurationResponse,
    StereoCameraConfigureBatchRequest,
    StereoCameraConfigureRequest,
    StereoCameraInfo,
    StereoCameraInfoResponse,
    StereoCameraOpenBatchRequest,
    StereoCameraOpenRequest,
    StereoCameraQueryRequest,
    StereoCameraStatus,
    StereoCameraStatusResponse,
    StereoCaptureBatchRequest,
    StereoCaptureBatchResponse,
    StereoCaptureBatchResult,
    StereoCaptureRequest,
    StereoCaptureResponse,
    StereoCaptureResult,
    SystemDiagnostics,
    SystemDiagnosticsResponse,
)
from mindtrace.hardware.core.exceptions import (
    CameraNotFoundError,
)
from mindtrace.hardware.stereo_cameras import AsyncStereoCamera, BaslerStereoAceBackend
from mindtrace.services import Service


class StereoCameraService(Service):
    """
    Stereo Camera Management Service.

    Provides comprehensive REST API and MCP tools for managing stereo cameras
    with multi-component capture capabilities (intensity, disparity, point clouds).

    Supported Operations:
    - Backend discovery and information
    - Camera lifecycle management (open, close, status)
    - Multi-component capture (intensity + disparity)
    - Point cloud generation with optional color
    - Camera configuration (depth range, illumination, binning, quality, exposure, gain)
    - Batch operations for multiple cameras
    - System diagnostics and monitoring
    """

    def __init__(self, **kwargs):
        """Initialize StereoCameraService.

        Args:
            **kwargs: Additional arguments passed to Service base class
        """
        super().__init__(
            summary="Stereo Camera Management Service",
            description="REST API and MCP tools for comprehensive stereo camera management and 3D capture",
            **kwargs,
        )

        # Active camera storage
        self._cameras: Dict[str, AsyncStereoCamera] = {}

        # Active streams tracking
        self._active_streams: Dict[str, Dict] = {}

        # Statistics
        self._start_time = time.time()
        self._total_captures = 0
        self._total_point_clouds = 0

        # Setup CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register REST endpoints
        self._register_endpoints()

    def _register_endpoints(self):
        """Register all REST API endpoints."""

        # Backend & Discovery Endpoints
        @self.app.get("/stereocameras/backends", response_model=BackendsResponse)
        async def get_backends():
            """Get list of available stereo camera backends."""
            try:
                backends = ["BaslerStereoAce"]
                return BackendsResponse(success=True, message="Backends retrieved", data=backends)
            except Exception as e:
                return BackendsResponse(success=False, message=f"Failed to get backends: {e}", data=[])

        @self.app.get("/stereocameras/backends/info", response_model=BackendInfoResponse)
        async def get_backend_info():
            """Get detailed information about stereo camera backends."""
            try:
                backends_info = {
                    "BaslerStereoAce": BackendInfo(
                        name="BaslerStereoAce",
                        available=True,
                        type="hardware",
                        sdk_required=True,
                        description="Basler Stereo ace (dual ace2 Pro + pattern projector)",
                    )
                }
                return BackendInfoResponse(success=True, message="Backend information retrieved", data=backends_info)
            except Exception as e:
                return BackendInfoResponse(success=False, message=f"Failed to get backend info: {e}", data={})

        @self.app.post("/stereocameras/discover", response_model=ListResponse)
        async def discover_cameras(request: BackendFilterRequest):
            """Discover available stereo cameras."""
            try:
                cameras = BaslerStereoAceBackend.discover()
                # Format as Backend:serial
                camera_list = [f"BaslerStereoAce:{serial}" for serial in cameras]
                return ListResponse(success=True, message=f"Found {len(camera_list)} stereo cameras", data=camera_list)
            except Exception as e:
                return ListResponse(success=False, message=f"Discovery failed: {e}", data=[])

        # Lifecycle Endpoints
        @self.app.post("/stereocameras/open", response_model=BoolResponse)
        async def open_camera(request: StereoCameraOpenRequest):
            """Open a stereo camera connection."""
            try:
                camera_name = request.camera

                if camera_name in self._cameras:
                    return BoolResponse(success=True, message="Camera already open", data=True)

                # Create and open async camera
                camera = await AsyncStereoCamera.open(camera_name)
                self._cameras[camera_name] = camera

                return BoolResponse(success=True, message=f"Camera {camera_name} opened", data=True)
            except Exception as e:
                return BoolResponse(success=False, message=f"Failed to open camera: {e}", data=False)

        @self.app.post("/stereocameras/open/batch", response_model=BatchOperationResponse)
        async def open_cameras_batch(request: StereoCameraOpenBatchRequest):
            """Open multiple stereo cameras."""
            results = []
            successful = 0
            failed = 0

            for camera_name in request.cameras:
                try:
                    if camera_name not in self._cameras:
                        camera = await AsyncStereoCamera.open(camera_name)
                        self._cameras[camera_name] = camera
                        successful += 1
                        results.append(BatchOperationResult(camera=camera_name, success=True, message="Opened"))
                    else:
                        successful += 1
                        results.append(BatchOperationResult(camera=camera_name, success=True, message="Already open"))
                except Exception as e:
                    failed += 1
                    results.append(BatchOperationResult(camera=camera_name, success=False, message=str(e)))

            data = {"successful": successful, "failed": failed, "results": [r.model_dump() for r in results]}
            return BatchOperationResponse(
                success=True, message=f"Batch open: {successful} successful, {failed} failed", data=data
            )

        @self.app.post("/stereocameras/close", response_model=BoolResponse)
        async def close_camera(request: StereoCameraCloseRequest):
            """Close a stereo camera connection."""
            try:
                camera_name = request.camera

                if camera_name not in self._cameras:
                    return BoolResponse(success=False, message="Camera not found", data=False)

                camera = self._cameras.pop(camera_name)
                await camera.close()

                return BoolResponse(success=True, message=f"Camera {camera_name} closed", data=True)
            except Exception as e:
                return BoolResponse(success=False, message=f"Failed to close camera: {e}", data=False)

        @self.app.post("/stereocameras/close/batch", response_model=BatchOperationResponse)
        async def close_cameras_batch(request: StereoCameraCloseBatchRequest):
            """Close multiple stereo cameras."""
            results = []
            successful = 0
            failed = 0

            for camera_name in request.cameras:
                try:
                    if camera_name in self._cameras:
                        camera = self._cameras.pop(camera_name)
                        await camera.close()
                        successful += 1
                        results.append(BatchOperationResult(camera=camera_name, success=True, message="Closed"))
                    else:
                        failed += 1
                        results.append(BatchOperationResult(camera=camera_name, success=False, message="Not found"))
                except Exception as e:
                    failed += 1
                    results.append(BatchOperationResult(camera=camera_name, success=False, message=str(e)))

            data = {"successful": successful, "failed": failed, "results": [r.model_dump() for r in results]}
            return BatchOperationResponse(
                success=True, message=f"Batch close: {successful} successful, {failed} failed", data=data
            )

        @self.app.post("/stereocameras/close/all", response_model=BoolResponse)
        async def close_all_cameras():
            """Close all active stereo cameras."""
            try:
                for camera in list(self._cameras.values()):
                    await camera.close()
                self._cameras.clear()
                return BoolResponse(success=True, message="All cameras closed", data=True)
            except Exception as e:
                return BoolResponse(success=False, message=f"Failed to close all cameras: {e}", data=False)

        @self.app.get("/stereocameras/active", response_model=ActiveStereoCamerasResponse)
        async def get_active_cameras():
            """Get list of active stereo cameras."""
            camera_names = list(self._cameras.keys())
            return ActiveStereoCamerasResponse(
                success=True, message=f"{len(camera_names)} active cameras", data=camera_names
            )

        # Status & Information Endpoints
        @self.app.post("/stereocameras/status", response_model=StereoCameraStatusResponse)
        async def get_camera_status(request: StereoCameraQueryRequest):
            """Get stereo camera status."""
            try:
                camera_name = request.camera
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                # Get trigger mode
                trigger_mode = await camera.get_trigger_mode()

                status = StereoCameraStatus(
                    name=camera.name,
                    is_open=camera.is_open,
                    backend="BaslerStereoAce",
                    has_calibration=camera.calibration is not None,
                    trigger_mode=trigger_mode,
                )

                return StereoCameraStatusResponse(success=True, message="Status retrieved", data=status)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

        @self.app.post("/stereocameras/info", response_model=StereoCameraInfoResponse)
        async def get_camera_info(request: StereoCameraQueryRequest):
            """Get detailed stereo camera information."""
            try:
                camera_name = request.camera
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                # Extract serial number from camera name
                serial = camera_name.split(":")[-1] if ":" in camera_name else None

                # Get trigger modes
                trigger_modes = await camera.get_trigger_modes()

                calibration_info = None
                if camera.calibration:
                    calibration_info = {
                        "baseline_mm": camera.calibration.baseline_mm,
                        "focal_length_px": camera.calibration.focal_length_px,
                        "has_rectification": camera.calibration.rectification_map_left is not None,
                    }

                info = StereoCameraInfo(
                    name=camera.name,
                    backend="BaslerStereoAce",
                    serial_number=serial,
                    has_calibration=camera.calibration is not None,
                    calibration_info=calibration_info,
                    trigger_modes=trigger_modes,
                )

                return StereoCameraInfoResponse(success=True, message="Information retrieved", data=info)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

        @self.app.get("/stereocameras/{camera_name}/calibration")
        async def get_calibration(camera_name: str):
            """Get full calibration data including Q matrix for 2D-to-3D projection."""
            try:
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                if camera.calibration is None:
                    raise HTTPException(status_code=400, detail="Camera not calibrated")

                calib = camera.calibration

                return {
                    "success": True,
                    "message": "Calibration data retrieved",
                    "data": {
                        "baseline_m": float(calib.baseline),
                        "baseline_mm": float(calib.baseline * 1000),
                        "focal_length_px": float(calib.focal_length),
                        "principal_point_u": float(calib.principal_point_u),
                        "principal_point_v": float(calib.principal_point_v),
                        "scale3d": float(calib.scale3d),
                        "offset3d": float(calib.offset3d),
                        "Q_matrix": calib.Q.tolist(),  # 4x4 reprojection matrix
                        "Q_shape": list(calib.Q.shape),
                    },
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # Configuration Endpoints
        @self.app.post("/stereocameras/configure", response_model=BoolResponse)
        async def configure_camera(request: StereoCameraConfigureRequest):
            """Configure stereo camera parameters."""
            try:
                camera_name = request.camera
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                # Log configuration being applied
                self.logger.info(f"Configuring camera {camera_name} with parameters: {request.properties}")

                await camera.configure(**request.properties)

                self.logger.info(
                    f"Successfully configured camera {camera_name} with {len(request.properties)} parameters"
                )

                return BoolResponse(success=True, message="Camera configured", data=True)
            except Exception as e:
                self.logger.error(f"Failed to configure camera {camera_name}: {e}")
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post("/stereocameras/configure/batch", response_model=BatchOperationResponse)
        async def configure_cameras_batch(request: StereoCameraConfigureBatchRequest):
            """Configure multiple stereo cameras."""
            results = []
            successful = 0
            failed = 0

            for camera_name, properties in request.configurations.items():
                try:
                    if camera_name not in self._cameras:
                        raise CameraNotFoundError(f"Camera {camera_name} not found")

                    camera = self._cameras[camera_name]
                    await camera.configure(**properties)
                    successful += 1
                    results.append(BatchOperationResult(camera=camera_name, success=True, message="Configured"))
                except Exception as e:
                    failed += 1
                    results.append(BatchOperationResult(camera=camera_name, success=False, message=str(e)))

            data = {"successful": successful, "failed": failed, "results": [r.model_dump() for r in results]}
            return BatchOperationResponse(
                success=True, message=f"Batch configure: {successful} successful, {failed} failed", data=data
            )

        @self.app.post("/stereocameras/configuration", response_model=StereoCameraConfigurationResponse)
        async def get_camera_configuration(request: StereoCameraQueryRequest):
            """Get current stereo camera configuration."""
            try:
                camera_name = request.camera
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                # Get all configuration parameters
                exposure_time = await camera.get_exposure_time()
                gain = await camera.get_gain()
                depth_quality = await camera.get_depth_quality()
                pixel_format = await camera.get_pixel_format()
                binning = await camera.get_binning()
                illumination_mode = await camera.get_illumination_mode()
                depth_range = await camera.get_depth_range()
                trigger_mode = await camera.get_trigger_mode()

                config = StereoCameraConfiguration(
                    exposure_time=exposure_time,
                    gain=gain,
                    depth_quality=depth_quality,
                    pixel_format=pixel_format,
                    binning=binning,
                    illumination_mode=illumination_mode,
                    depth_range=depth_range,
                    trigger_mode=trigger_mode,
                )

                return StereoCameraConfigurationResponse(success=True, message="Configuration retrieved", data=config)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

        # Capture Endpoints
        @self.app.post("/stereocameras/capture", response_model=StereoCaptureResponse)
        async def capture_stereo_pair(request: StereoCaptureRequest):
            """Capture stereo data (intensity + disparity)."""
            try:
                camera_name = request.camera
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                # Capture stereo data
                result = await camera.capture(
                    enable_intensity=request.enable_intensity,
                    enable_disparity=request.enable_disparity,
                    calibrate_disparity=request.calibrate_disparity,
                    timeout_ms=request.timeout_ms,
                )

                self._total_captures += 1

                # Save if requested
                if request.save_intensity_path and result.intensity is not None:
                    import cv2

                    cv2.imwrite(request.save_intensity_path, result.intensity)

                if request.save_disparity_path and result.disparity is not None:
                    import cv2

                    cv2.imwrite(request.save_disparity_path, result.disparity)

                capture_result = StereoCaptureResult(
                    camera_name=camera_name,
                    frame_number=result.frame_number,
                    intensity_shape=result.intensity.shape if result.intensity is not None else None,
                    disparity_shape=result.disparity.shape if result.disparity is not None else None,
                    intensity_saved_path=request.save_intensity_path,
                    disparity_saved_path=request.save_disparity_path,
                    capture_timestamp=datetime.now(timezone.utc).isoformat(),
                )

                return StereoCaptureResponse(success=True, message="Stereo capture successful", data=capture_result)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/stereocameras/capture/batch", response_model=StereoCaptureBatchResponse)
        async def capture_stereo_batch(request: StereoCaptureBatchRequest):
            """Capture stereo data from multiple cameras."""
            results = []
            successful = 0
            failed = 0
            errors = {}

            for capture_config in request.captures:
                camera_name = capture_config.get("camera")
                try:
                    if not camera_name:
                        raise ValueError("Camera name required")

                    if camera_name not in self._cameras:
                        raise CameraNotFoundError(f"Camera {camera_name} not found")

                    camera = self._cameras[camera_name]

                    # Capture
                    result = await camera.capture(
                        enable_intensity=capture_config.get("enable_intensity", True),
                        enable_disparity=capture_config.get("enable_disparity", True),
                        calibrate_disparity=capture_config.get("calibrate_disparity", True),
                        timeout_ms=capture_config.get("timeout_ms", 20000),
                    )

                    self._total_captures += 1

                    capture_result = StereoCaptureResult(
                        camera_name=camera_name,
                        frame_number=result.frame_number,
                        intensity_shape=result.intensity.shape if result.intensity is not None else None,
                        disparity_shape=result.disparity.shape if result.disparity is not None else None,
                        intensity_saved_path=capture_config.get("save_intensity_path"),
                        disparity_saved_path=capture_config.get("save_disparity_path"),
                        capture_timestamp=datetime.now(timezone.utc).isoformat(),
                    )

                    results.append(capture_result)
                    successful += 1

                except Exception as e:
                    failed += 1
                    errors[camera_name or "unknown"] = str(e)

            batch_result = StereoCaptureBatchResult(
                successful=successful, failed=failed, results=results, errors=errors
            )

            return StereoCaptureBatchResponse(
                success=True, message=f"Batch capture: {successful} successful, {failed} failed", data=batch_result
            )

        # Point Cloud Endpoints
        @self.app.post("/stereocameras/capture/pointcloud", response_model=PointCloudResponse)
        async def capture_point_cloud(request: PointCloudCaptureRequest):
            """Capture and generate 3D point cloud."""
            try:
                camera_name = request.camera
                if camera_name not in self._cameras:
                    raise CameraNotFoundError(f"Camera {camera_name} not found")

                camera = self._cameras[camera_name]

                # Capture point cloud
                point_cloud = await camera.capture_point_cloud(
                    include_colors=request.include_colors,
                    remove_outliers=request.remove_outliers,
                    downsample_factor=request.downsample_factor,
                )

                self._total_point_clouds += 1

                # Save if requested
                if request.save_path:
                    point_cloud.save_ply(request.save_path)

                result = PointCloudResult(
                    camera_name=camera_name,
                    num_points=point_cloud.num_points,
                    has_colors=point_cloud.colors is not None,
                    saved_path=request.save_path,
                    points_shape=point_cloud.points.shape if point_cloud.points is not None else None,
                    colors_shape=point_cloud.colors.shape if point_cloud.colors is not None else None,
                    capture_timestamp=datetime.now(timezone.utc).isoformat(),
                )

                return PointCloudResponse(success=True, message="Point cloud captured", data=result)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/stereocameras/capture/pointcloud/batch", response_model=PointCloudBatchResponse)
        async def capture_point_cloud_batch(request: PointCloudCaptureBatchRequest):
            """Capture point clouds from multiple cameras."""
            results = []
            successful = 0
            failed = 0
            errors = {}

            for capture_config in request.captures:
                camera_name = capture_config.get("camera")
                try:
                    if not camera_name:
                        raise ValueError("Camera name required")

                    if camera_name not in self._cameras:
                        raise CameraNotFoundError(f"Camera {camera_name} not found")

                    camera = self._cameras[camera_name]

                    # Capture point cloud
                    point_cloud = await camera.capture_point_cloud(
                        include_colors=capture_config.get("include_colors", True),
                        remove_outliers=capture_config.get("remove_outliers", False),
                        downsample_factor=capture_config.get("downsample_factor", 1),
                    )

                    self._total_point_clouds += 1

                    result = PointCloudResult(
                        camera_name=camera_name,
                        num_points=point_cloud.num_points,
                        has_colors=point_cloud.colors is not None,
                        saved_path=capture_config.get("save_path"),
                        points_shape=point_cloud.points.shape if point_cloud.points is not None else None,
                        colors_shape=point_cloud.colors.shape if point_cloud.colors is not None else None,
                        capture_timestamp=datetime.now(timezone.utc).isoformat(),
                    )

                    results.append(result)
                    successful += 1

                except Exception as e:
                    failed += 1
                    errors[camera_name or "unknown"] = str(e)

            batch_result = PointCloudBatchResult(successful=successful, failed=failed, results=results, errors=errors)

            return PointCloudBatchResponse(
                success=True,
                message=f"Batch point cloud capture: {successful} successful, {failed} failed",
                data=batch_result,
            )

        # System Diagnostics
        @self.app.get("/system/diagnostics", response_model=SystemDiagnosticsResponse)
        async def get_system_diagnostics():
            """Get system diagnostics and statistics."""
            import psutil

            uptime = time.time() - self._start_time
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024

            diagnostics = SystemDiagnostics(
                active_cameras=len(self._cameras),
                total_captures=self._total_captures,
                uptime_seconds=uptime,
                memory_usage_mb=memory_mb,
            )

            return SystemDiagnosticsResponse(success=True, message="Diagnostics retrieved", data=diagnostics)

        # Health Check
        @self.app.get("/health")
        async def health_check():
            """Service health check."""
            return {
                "status": "healthy",
                "service": "stereo_camera_manager",
                "version": "1.0.0",
                "active_cameras": len(self._cameras),
                "uptime_seconds": time.time() - self._start_time,
            }

        # Streaming endpoints
        @self.app.post("/stereocameras/stream/start")
        async def start_stream(camera: str, quality: int = 85, fps: int = 10):
            """Start stereo camera stream."""
            import os

            if camera not in self._cameras:
                raise HTTPException(status_code=404, detail=f"Camera {camera} not found")

            # Get API host/port from environment
            api_host = os.getenv("STEREO_API_HOST", "localhost")
            api_port = os.getenv("STEREO_API_PORT", "8004")
            stream_url = f"http://{api_host}:{api_port}/stream/{camera.replace(':', '_')}"

            # Track active stream
            self._active_streams[camera] = {
                "stream_url": stream_url,
                "start_time": datetime.now(timezone.utc),
                "quality": quality,
                "fps": fps,
            }

            return {
                "success": True,
                "message": f"Stream started for camera '{camera}'",
                "data": {
                    "camera": camera,
                    "streaming": True,
                    "stream_url": stream_url,
                    "start_time": datetime.now(timezone.utc).isoformat(),
                },
            }

        @self.app.post("/stereocameras/stream/stop")
        async def stop_stream(camera: str):
            """Stop stereo camera stream."""
            was_streaming = camera in self._active_streams
            if was_streaming:
                del self._active_streams[camera]

            return {"success": True, "message": f"Stream stopped for camera '{camera}'", "data": True}

        @self.app.get("/stereocameras/stream/active")
        async def get_active_streams():
            """Get list of active streams."""
            return {"success": True, "message": "Active streams retrieved", "data": list(self._active_streams.keys())}

        @self.app.get("/stream/{camera_name}")
        async def serve_stereo_stream(camera_name: str):
            """Serve MJPEG video stream for stereo camera (intensity image)."""
            import asyncio

            import cv2
            import numpy as np
            from fastapi.responses import StreamingResponse

            # Replace first underscore back to colon
            actual_camera_name = camera_name.replace("_", ":", 1)

            # Check if camera is active
            if actual_camera_name not in self._cameras:
                raise HTTPException(status_code=404, detail=f"Camera '{actual_camera_name}' not initialized")

            camera = self._cameras[actual_camera_name]

            # Get streaming parameters
            stream_info = self._active_streams.get(actual_camera_name, {})
            quality = stream_info.get("quality", 85)
            fps = stream_info.get("fps", 10)
            frame_delay = 1.0 / fps

            async def generate_mjpeg_stream():
                """Generate MJPEG stream from stereo camera intensity images."""
                consecutive_timeouts = 0
                max_consecutive_timeouts = 10  # Increased for resilience during camera reconfiguration
                capture_timeout = 10.0

                while True:
                    try:
                        # Capture stereo data (intensity only for streaming)
                        result = await asyncio.wait_for(
                            camera.capture(
                                enable_intensity=True, enable_disparity=False, timeout_ms=int(capture_timeout * 1000)
                            ),
                            timeout=capture_timeout,
                        )

                        # Reset timeout counter and log recovery if we had timeouts
                        if consecutive_timeouts > 0:
                            self.logger.info(
                                f"Stream recovered for camera '{actual_camera_name}' after {consecutive_timeouts} timeout(s)"
                            )
                        consecutive_timeouts = 0

                        if result.intensity is not None:
                            frame = result.intensity

                            # Ensure uint8
                            if frame.dtype != np.uint8:
                                frame = (frame * 255).astype(np.uint8)

                            # Encode as JPEG
                            success, jpeg_data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])

                            if success:
                                frame_data = jpeg_data.tobytes()
                                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n")

                        # Control frame rate
                        await asyncio.sleep(frame_delay)

                    except asyncio.TimeoutError:
                        consecutive_timeouts += 1
                        if consecutive_timeouts == 1:
                            self.logger.warning(
                                f"Stream timeout for camera '{actual_camera_name}' (may be due to reconfiguration)"
                            )
                        elif consecutive_timeouts >= max_consecutive_timeouts:
                            error_msg = f"Stream terminated: Camera '{actual_camera_name}' - {max_consecutive_timeouts} consecutive timeouts"
                            self.logger.error(error_msg)
                            yield (b"--frame\r\nContent-Type: text/plain\r\n\r\n" + error_msg.encode() + b"\r\n")
                            break
                        await asyncio.sleep(1.0)
                        continue

                    except Exception:
                        if actual_camera_name not in self._cameras:
                            break
                        await asyncio.sleep(0.1)
                        continue

            return StreamingResponse(
                generate_mjpeg_stream(),
                media_type="multipart/x-mixed-replace; boundary=frame",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
