"""
Scanner3DService - Service-based API for 3D scanner management.

This service provides comprehensive REST API and MCP tools for managing
3D scanners (Photoneo PhoXi, etc.) with multi-component capture capabilities.
"""

import time
from datetime import datetime, timezone
from typing import Dict

import numpy as np
import psutil
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from mindtrace.hardware.core.exceptions import (
    CameraNotFoundError,
)
from mindtrace.hardware.core.types import ServiceStatus
from mindtrace.hardware.scanners_3d import AsyncScanner3D, PhotoneoBackend
from mindtrace.hardware.scanners_3d.core.models import (
    ScannerConfiguration as CoreScannerConfiguration,
)
from mindtrace.hardware.services.scanners_3d.models import (
    # Responses
    ActiveScannersResponse,
    # Requests
    BackendFilterRequest,
    BackendInfo,
    BackendInfoResponse,
    BackendsResponse,
    BatchOperationResponse,
    BoolResponse,
    HealthCheckResponse,
    ListResponse,
    PointCloudBatchResponse,
    PointCloudBatchResult,
    PointCloudCaptureBatchRequest,
    PointCloudCaptureRequest,
    PointCloudResponse,
    PointCloudResult,
    ScanCaptureBatchRequest,
    ScanCaptureBatchResponse,
    ScanCaptureBatchResult,
    ScanCaptureRequest,
    ScanCaptureResponse,
    ScanCaptureResult,
    ScannerCapabilities,
    ScannerCapabilitiesResponse,
    ScannerCloseBatchRequest,
    ScannerCloseRequest,
    ScannerConfiguration,
    ScannerConfigurationResponse,
    ScannerConfigureBatchRequest,
    ScannerConfigureRequest,
    ScannerInfo,
    ScannerInfoResponse,
    ScannerOpenBatchRequest,
    ScannerOpenRequest,
    ScannerQueryRequest,
    ScannerStatus,
    ScannerStatusResponse,
    SystemDiagnostics,
    SystemDiagnosticsResponse,
)
from mindtrace.hardware.services.scanners_3d.schemas import ALL_SCHEMAS, HealthSchema
from mindtrace.services import Service


class Scanner3DService(Service):
    """
    3D Scanner Management Service.

    Provides comprehensive REST API and MCP tools for managing 3D scanners
    with multi-component capture capabilities (range, intensity, confidence,
    normals, color, point clouds).

    Supported Operations:
    - Backend discovery and information
    - Scanner lifecycle management (open, close, status)
    - Multi-component capture (range, intensity, confidence, normals, color)
    - Point cloud generation with optional color and confidence
    - Scanner configuration (exposure, trigger mode)
    - Batch operations for multiple scanners
    - System diagnostics and monitoring
    """

    def __init__(self, **kwargs):
        """Initialize Scanner3DService.

        Args:
            **kwargs: Additional arguments passed to Service base class
        """
        super().__init__(
            summary="3D Scanner Management Service",
            description="REST API and MCP tools for comprehensive 3D scanner management and point cloud capture",
            **kwargs,
        )

        # Active scanner storage
        self._scanners: Dict[str, AsyncScanner3D] = {}

        # Statistics
        self._start_time = time.time()
        self._total_scans = 0
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
        """Register all REST API endpoints using add_endpoint pattern."""

        # Health check endpoint
        self.add_endpoint("health", self.health_check, HealthSchema, methods=["GET"], as_tool=False)

        # Backend & Discovery
        self.add_endpoint(
            "scanners/backends", self.get_backends, ALL_SCHEMAS["get_backends"], methods=["GET"], as_tool=True
        )
        self.add_endpoint(
            "scanners/backends/info",
            self.get_backend_info,
            ALL_SCHEMAS["get_backend_info"],
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint("scanners/discover", self.discover_scanners, ALL_SCHEMAS["discover_scanners"], as_tool=True)

        # Scanner Lifecycle
        self.add_endpoint("scanners/open", self.open_scanner, ALL_SCHEMAS["open_scanner"], as_tool=True)
        self.add_endpoint(
            "scanners/open/batch", self.open_scanners_batch, ALL_SCHEMAS["open_scanners_batch"], as_tool=True
        )
        self.add_endpoint("scanners/close", self.close_scanner, ALL_SCHEMAS["close_scanner"], as_tool=True)
        self.add_endpoint(
            "scanners/close/batch", self.close_scanners_batch, ALL_SCHEMAS["close_scanners_batch"], as_tool=True
        )
        self.add_endpoint(
            "scanners/close/all", self.close_all_scanners, ALL_SCHEMAS["close_all_scanners"], as_tool=True
        )
        self.add_endpoint(
            "scanners/active",
            self.get_active_scanners,
            ALL_SCHEMAS["get_active_scanners"],
            methods=["GET"],
            as_tool=True,
        )

        # Scanner Status & Information
        self.add_endpoint("scanners/status", self.get_scanner_status, ALL_SCHEMAS["get_scanner_status"], as_tool=True)
        self.add_endpoint("scanners/info", self.get_scanner_info, ALL_SCHEMAS["get_scanner_info"], as_tool=True)
        self.add_endpoint(
            "system/diagnostics",
            self.get_system_diagnostics,
            ALL_SCHEMAS["get_system_diagnostics"],
            methods=["GET"],
            as_tool=True,
        )

        # Scanner Configuration
        self.add_endpoint(
            "scanners/capabilities",
            self.get_scanner_capabilities,
            ALL_SCHEMAS["get_scanner_capabilities"],
            as_tool=True,
        )
        self.add_endpoint("scanners/configure", self.configure_scanner, ALL_SCHEMAS["configure_scanner"], as_tool=True)
        self.add_endpoint(
            "scanners/configure/batch",
            self.configure_scanners_batch,
            ALL_SCHEMAS["configure_scanners_batch"],
            as_tool=True,
        )
        self.add_endpoint(
            "scanners/config/get",
            self.get_scanner_configuration,
            ALL_SCHEMAS["get_scanner_configuration"],
            as_tool=True,
        )

        # Scan Capture
        self.add_endpoint("scanners/capture", self.capture_scan, ALL_SCHEMAS["capture_scan"], as_tool=True)
        self.add_endpoint(
            "scanners/capture/batch", self.capture_scan_batch, ALL_SCHEMAS["capture_scan_batch"], as_tool=True
        )

        # Point Cloud Capture
        self.add_endpoint(
            "scanners/capture/pointcloud", self.capture_point_cloud, ALL_SCHEMAS["capture_pointcloud"], as_tool=True
        )
        self.add_endpoint(
            "scanners/capture/pointcloud/batch",
            self.capture_point_cloud_batch,
            ALL_SCHEMAS["capture_pointcloud_batch"],
            as_tool=True,
        )

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> HealthCheckResponse:
        """Health check endpoint."""
        try:
            backends = self._get_available_backends()
            return HealthCheckResponse(
                status=ServiceStatus.HEALTHY,
                service="scanner_3d_service",
                version="1.0.0",
                backends=backends,
                active_scanners=len(self._scanners),
                uptime_seconds=time.time() - self._start_time,
            )
        except Exception as e:
            return HealthCheckResponse(
                status=ServiceStatus.UNHEALTHY,
                service="scanner_3d_service",
                version="1.0.0",
                error=str(e),
            )

    # =========================================================================
    # Backend & Discovery
    # =========================================================================

    def _get_available_backends(self):
        """Get list of available backend names."""
        backends = []
        try:
            PhotoneoBackend.discover()
            backends.append("Photoneo")
        except Exception:
            pass
        return backends

    async def get_backends(self) -> BackendsResponse:
        """Get available scanner backends."""
        backends = self._get_available_backends()
        return BackendsResponse(success=True, message=f"Found {len(backends)} backends", data=backends)

    async def get_backend_info(self) -> BackendInfoResponse:
        """Get detailed backend information."""
        info = {}

        # Check Photoneo backend
        try:
            PhotoneoBackend.discover()
            info["Photoneo"] = BackendInfo(
                name="Photoneo",
                available=True,
                type="hardware",
                sdk_required=True,
                description="Photoneo PhoXi structured light 3D scanners via Harvesters/GigE Vision",
            )
        except Exception:
            info["Photoneo"] = BackendInfo(
                name="Photoneo",
                available=False,
                type="hardware",
                sdk_required=True,
                description="Photoneo PhoXi - requires Harvesters and Matrix Vision SDK",
            )

        return BackendInfoResponse(success=True, message="Backend information retrieved", data=info)

    async def discover_scanners(self, request: BackendFilterRequest) -> ListResponse:
        """Discover available 3D scanners."""
        scanners = []

        try:
            if request.backend is None or request.backend == "Photoneo":
                try:
                    photoneo_scanners = await PhotoneoBackend.discover_async()
                    scanners.extend([f"Photoneo:{sn}" for sn in photoneo_scanners])
                except Exception:
                    pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        return ListResponse(success=True, message=f"Found {len(scanners)} scanners", data=scanners)

    # =========================================================================
    # Scanner Lifecycle
    # =========================================================================

    async def open_scanner(self, request: ScannerOpenRequest) -> BoolResponse:
        """Open a 3D scanner connection."""
        scanner_name = request.scanner

        if scanner_name in self._scanners:
            return BoolResponse(success=True, message=f"Scanner {scanner_name} already open", data=True)

        try:
            scanner = await AsyncScanner3D.open(scanner_name)
            self._scanners[scanner_name] = scanner
            return BoolResponse(success=True, message=f"Scanner {scanner_name} opened successfully", data=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def open_scanners_batch(self, request: ScannerOpenBatchRequest) -> BatchOperationResponse:
        """Open multiple scanners."""
        results = {"successful": 0, "failed": 0, "results": []}

        for scanner_name in request.scanners:
            try:
                if scanner_name not in self._scanners:
                    scanner = await AsyncScanner3D.open(scanner_name)
                    self._scanners[scanner_name] = scanner
                results["successful"] += 1
                results["results"].append({"scanner": scanner_name, "success": True, "message": "Opened"})
            except Exception as e:
                results["failed"] += 1
                results["results"].append({"scanner": scanner_name, "success": False, "message": str(e)})

        return BatchOperationResponse(
            success=results["failed"] == 0,
            message=f"Opened {results['successful']}/{len(request.scanners)} scanners",
            data=results,
        )

    async def close_scanner(self, request: ScannerCloseRequest) -> BoolResponse:
        """Close a 3D scanner connection."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            return BoolResponse(success=False, message=f"Scanner {scanner_name} not found", data=False)

        try:
            await self._scanners[scanner_name].close()
            del self._scanners[scanner_name]
            return BoolResponse(success=True, message=f"Scanner {scanner_name} closed", data=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def close_scanners_batch(self, request: ScannerCloseBatchRequest) -> BatchOperationResponse:
        """Close multiple scanners."""
        results = {"successful": 0, "failed": 0, "results": []}

        for scanner_name in request.scanners:
            try:
                if scanner_name in self._scanners:
                    await self._scanners[scanner_name].close()
                    del self._scanners[scanner_name]
                results["successful"] += 1
                results["results"].append({"scanner": scanner_name, "success": True, "message": "Closed"})
            except Exception as e:
                results["failed"] += 1
                results["results"].append({"scanner": scanner_name, "success": False, "message": str(e)})

        return BatchOperationResponse(
            success=results["failed"] == 0,
            message=f"Closed {results['successful']}/{len(request.scanners)} scanners",
            data=results,
        )

    async def close_all_scanners(self) -> BatchOperationResponse:
        """Close all active scanners."""
        scanner_names = list(self._scanners.keys())
        results = {"successful": 0, "failed": 0, "results": []}

        for scanner_name in scanner_names:
            try:
                await self._scanners[scanner_name].close()
                del self._scanners[scanner_name]
                results["successful"] += 1
                results["results"].append({"scanner": scanner_name, "success": True, "message": "Closed"})
            except Exception as e:
                results["failed"] += 1
                results["results"].append({"scanner": scanner_name, "success": False, "message": str(e)})

        return BatchOperationResponse(
            success=results["failed"] == 0, message=f"Closed {results['successful']} scanners", data=results
        )

    async def get_active_scanners(self) -> ActiveScannersResponse:
        """Get list of active scanners."""
        return ActiveScannersResponse(
            success=True, message=f"{len(self._scanners)} active scanners", data=list(self._scanners.keys())
        )

    # =========================================================================
    # Scanner Status & Information
    # =========================================================================

    async def get_scanner_status(self, request: ScannerQueryRequest) -> ScannerStatusResponse:
        """Get scanner status."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        scanner = self._scanners[scanner_name]
        backend = scanner_name.split(":")[0] if ":" in scanner_name else "Unknown"

        status = ScannerStatus(name=scanner_name, is_open=scanner.is_open, backend=backend)

        return ScannerStatusResponse(success=True, message="Status retrieved", data=status)

    async def get_scanner_info(self, request: ScannerQueryRequest) -> ScannerInfoResponse:
        """Get scanner information."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        parts = scanner_name.split(":")
        backend = parts[0] if len(parts) > 0 else "Unknown"
        serial = parts[1] if len(parts) > 1 else None

        info = ScannerInfo(name=scanner_name, backend=backend, serial_number=serial)

        return ScannerInfoResponse(success=True, message="Info retrieved", data=info)

    async def get_system_diagnostics(self) -> SystemDiagnosticsResponse:
        """Get system diagnostics."""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024

        diagnostics = SystemDiagnostics(
            active_scanners=len(self._scanners),
            total_scans=self._total_scans,
            total_point_clouds=self._total_point_clouds,
            uptime_seconds=time.time() - self._start_time,
            memory_usage_mb=memory_mb,
        )

        return SystemDiagnosticsResponse(success=True, message="Diagnostics retrieved", data=diagnostics)

    # =========================================================================
    # Scanner Configuration
    # =========================================================================

    async def get_scanner_capabilities(self, request: ScannerQueryRequest) -> ScannerCapabilitiesResponse:
        """Get scanner capabilities and available settings."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        try:
            scanner = self._scanners[scanner_name]
            core_caps = await scanner.get_capabilities()

            # Convert core capabilities to service response model
            caps = ScannerCapabilities(
                has_range=core_caps.has_range,
                has_intensity=core_caps.has_intensity,
                has_confidence=core_caps.has_confidence,
                has_normal=core_caps.has_normal,
                has_color=core_caps.has_color,
                operation_modes=core_caps.operation_modes,
                coding_strategies=core_caps.coding_strategies,
                coding_qualities=core_caps.coding_qualities,
                texture_sources=core_caps.texture_sources,
                output_topologies=core_caps.output_topologies,
                exposure_range=core_caps.exposure_range,
                led_power_range=core_caps.led_power_range,
                laser_power_range=core_caps.laser_power_range,
                fps_range=core_caps.fps_range,
                depth_resolution=core_caps.depth_resolution,
                color_resolution=core_caps.color_resolution,
                model=core_caps.model,
                serial_number=core_caps.serial_number,
                firmware_version=core_caps.firmware_version,
            )

            return ScannerCapabilitiesResponse(success=True, message="Capabilities retrieved", data=caps)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def configure_scanner(self, request: ScannerConfigureRequest) -> BoolResponse:
        """Configure scanner parameters."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        try:
            scanner = self._scanners[scanner_name]

            # Build core configuration from request
            from mindtrace.hardware.scanners_3d.core.models import (
                CameraSpace,
                CodingQuality,
                CodingStrategy,
                HardwareTriggerSignal,
                OperationMode,
                OutputTopology,
                TextureSource,
                TriggerMode,
            )

            config = CoreScannerConfiguration()

            # Operation settings
            if request.operation_mode:
                config.operation_mode = OperationMode(request.operation_mode)
            if request.coding_strategy:
                config.coding_strategy = CodingStrategy(request.coding_strategy)
            if request.coding_quality:
                config.coding_quality = CodingQuality(request.coding_quality)
            if request.maximum_fps is not None:
                config.maximum_fps = request.maximum_fps

            # Exposure settings
            if request.exposure_time is not None:
                config.exposure_time = request.exposure_time
            if request.single_pattern_exposure is not None:
                config.single_pattern_exposure = request.single_pattern_exposure
            if request.shutter_multiplier is not None:
                config.shutter_multiplier = request.shutter_multiplier
            if request.scan_multiplier is not None:
                config.scan_multiplier = request.scan_multiplier
            if request.color_exposure is not None:
                config.color_exposure = request.color_exposure

            # Lighting settings
            if request.led_power is not None:
                config.led_power = request.led_power
            if request.laser_power is not None:
                config.laser_power = request.laser_power

            # Texture settings
            if request.texture_source:
                config.texture_source = TextureSource(request.texture_source)
            if request.camera_texture_source:
                config.camera_texture_source = TextureSource(request.camera_texture_source)

            # Output settings
            if request.output_topology:
                config.output_topology = OutputTopology(request.output_topology)
            if request.camera_space:
                config.camera_space = CameraSpace(request.camera_space)

            # Processing settings
            if request.normals_estimation_radius is not None:
                config.normals_estimation_radius = request.normals_estimation_radius
            if request.max_inaccuracy is not None:
                config.max_inaccuracy = request.max_inaccuracy
            if request.calibration_volume_only is not None:
                config.calibration_volume_only = request.calibration_volume_only
            if request.hole_filling is not None:
                config.hole_filling = request.hole_filling

            # Trigger settings
            if request.trigger_mode:
                config.trigger_mode = TriggerMode(request.trigger_mode)
            if request.hardware_trigger is not None:
                config.hardware_trigger = request.hardware_trigger
            if request.hardware_trigger_signal:
                config.hardware_trigger_signal = HardwareTriggerSignal(request.hardware_trigger_signal)

            await scanner.set_configuration(config)

            return BoolResponse(success=True, message="Scanner configured", data=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def configure_scanners_batch(self, request: ScannerConfigureBatchRequest) -> BatchOperationResponse:
        """Configure multiple scanners."""
        results = {"successful": 0, "failed": 0, "results": []}

        for scanner_name, properties in request.configurations.items():
            try:
                if scanner_name not in self._scanners:
                    raise CameraNotFoundError(f"Scanner {scanner_name} not found")

                # Create a configure request and call configure_scanner
                config_request = ScannerConfigureRequest(scanner=scanner_name, **properties)
                await self.configure_scanner(config_request)

                results["successful"] += 1
                results["results"].append({"scanner": scanner_name, "success": True, "message": "Configured"})
            except Exception as e:
                results["failed"] += 1
                results["results"].append({"scanner": scanner_name, "success": False, "message": str(e)})

        return BatchOperationResponse(
            success=results["failed"] == 0,
            message=f"Configured {results['successful']}/{len(request.configurations)} scanners",
            data=results,
        )

    async def get_scanner_configuration(self, request: ScannerQueryRequest) -> ScannerConfigurationResponse:
        """Get scanner configuration."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        try:
            scanner = self._scanners[scanner_name]
            core_config = await scanner.get_configuration()

            # Convert core config to service response model
            config = ScannerConfiguration(
                # Operation settings
                operation_mode=core_config.operation_mode.value if core_config.operation_mode else None,
                coding_strategy=core_config.coding_strategy.value if core_config.coding_strategy else None,
                coding_quality=core_config.coding_quality.value if core_config.coding_quality else None,
                maximum_fps=core_config.maximum_fps,
                # Exposure settings
                exposure_time=core_config.exposure_time,
                single_pattern_exposure=core_config.single_pattern_exposure,
                shutter_multiplier=core_config.shutter_multiplier,
                scan_multiplier=core_config.scan_multiplier,
                color_exposure=core_config.color_exposure,
                # Lighting settings
                led_power=core_config.led_power,
                laser_power=core_config.laser_power,
                # Texture settings
                texture_source=core_config.texture_source.value if core_config.texture_source else None,
                camera_texture_source=core_config.camera_texture_source.value
                if core_config.camera_texture_source
                else None,
                # Output settings
                output_topology=core_config.output_topology.value if core_config.output_topology else None,
                camera_space=core_config.camera_space.value if core_config.camera_space else None,
                # Processing settings
                normals_estimation_radius=core_config.normals_estimation_radius,
                max_inaccuracy=core_config.max_inaccuracy,
                calibration_volume_only=core_config.calibration_volume_only,
                hole_filling=core_config.hole_filling,
                # Trigger settings
                trigger_mode=core_config.trigger_mode.value if core_config.trigger_mode else None,
                hardware_trigger=core_config.hardware_trigger,
                hardware_trigger_signal=core_config.hardware_trigger_signal.value
                if core_config.hardware_trigger_signal
                else None,
            )

            return ScannerConfigurationResponse(success=True, message="Configuration retrieved", data=config)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # =========================================================================
    # Scan Capture
    # =========================================================================

    async def capture_scan(self, request: ScanCaptureRequest) -> ScanCaptureResponse:
        """Capture 3D scan data."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        try:
            scanner = self._scanners[scanner_name]

            result = await scanner.capture(
                timeout_ms=request.timeout_ms,
                enable_range=request.enable_range,
                enable_intensity=request.enable_intensity,
                enable_confidence=request.enable_confidence,
                enable_normal=request.enable_normal,
                enable_color=request.enable_color,
            )

            self._total_scans += 1

            # Save images if requested
            import cv2

            if request.save_range_path and result.range_map is not None:
                cv2.imwrite(request.save_range_path, result.range_map)

            if request.save_intensity_path and result.intensity is not None:
                cv2.imwrite(request.save_intensity_path, result.intensity)

            if request.save_confidence_path and result.confidence is not None:
                cv2.imwrite(request.save_confidence_path, result.confidence)

            if request.save_normal_path and result.normal_map is not None:
                # Convert normal vectors [-1,1] to uint8 [0,255] for visualization
                normal_vis = ((result.normal_map + 1) * 127.5).astype(np.uint8)
                cv2.imwrite(request.save_normal_path, normal_vis)

            if request.save_color_path and result.color is not None:
                cv2.imwrite(request.save_color_path, result.color)

            capture_result = ScanCaptureResult(
                scanner_name=scanner_name,
                frame_number=result.frame_number,
                range_shape=result.range_map.shape if result.range_map is not None else None,
                intensity_shape=result.intensity.shape if result.intensity is not None else None,
                confidence_shape=result.confidence.shape if result.confidence is not None else None,
                normal_shape=result.normal_map.shape if result.normal_map is not None else None,
                color_shape=result.color.shape if result.color is not None else None,
                range_saved_path=request.save_range_path if result.range_map is not None else None,
                intensity_saved_path=request.save_intensity_path if result.intensity is not None else None,
                confidence_saved_path=request.save_confidence_path if result.confidence is not None else None,
                normal_saved_path=request.save_normal_path if result.normal_map is not None else None,
                color_saved_path=request.save_color_path if result.color is not None else None,
                capture_timestamp=datetime.now(timezone.utc).isoformat(),
            )

            return ScanCaptureResponse(success=True, message="Scan captured", data=capture_result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def capture_scan_batch(self, request: ScanCaptureBatchRequest) -> ScanCaptureBatchResponse:
        """Capture scans from multiple scanners."""
        results = []
        successful = 0
        failed = 0
        errors = {}

        for capture_config in request.captures:
            scanner_name = capture_config.get("scanner")
            try:
                if not scanner_name:
                    raise ValueError("Scanner name required")

                if scanner_name not in self._scanners:
                    raise CameraNotFoundError(f"Scanner {scanner_name} not found")

                scanner = self._scanners[scanner_name]

                result = await scanner.capture(
                    timeout_ms=capture_config.get("timeout_ms", 10000),
                    enable_range=capture_config.get("enable_range", True),
                    enable_intensity=capture_config.get("enable_intensity", True),
                    enable_confidence=capture_config.get("enable_confidence", False),
                    enable_normal=capture_config.get("enable_normal", False),
                    enable_color=capture_config.get("enable_color", False),
                )

                self._total_scans += 1

                capture_result = ScanCaptureResult(
                    scanner_name=scanner_name,
                    frame_number=result.frame_number,
                    range_shape=result.range_map.shape if result.range_map is not None else None,
                    intensity_shape=result.intensity.shape if result.intensity is not None else None,
                    capture_timestamp=datetime.now(timezone.utc).isoformat(),
                )

                results.append(capture_result)
                successful += 1
            except Exception as e:
                failed += 1
                errors[scanner_name or "unknown"] = str(e)

        batch_result = ScanCaptureBatchResult(successful=successful, failed=failed, results=results, errors=errors)

        return ScanCaptureBatchResponse(
            success=failed == 0, message=f"Captured {successful}/{len(request.captures)} scans", data=batch_result
        )

    # =========================================================================
    # Point Cloud Capture
    # =========================================================================

    async def capture_point_cloud(self, request: PointCloudCaptureRequest) -> PointCloudResponse:
        """Capture and generate 3D point cloud."""
        scanner_name = request.scanner

        if scanner_name not in self._scanners:
            raise HTTPException(status_code=404, detail=f"Scanner {scanner_name} not found")

        try:
            scanner = self._scanners[scanner_name]

            point_cloud = await scanner.capture_point_cloud(
                include_colors=request.include_colors,
                include_confidence=request.include_confidence,
            )

            self._total_point_clouds += 1

            # Downsample if requested
            if request.downsample_factor > 1:
                point_cloud = point_cloud.downsample(request.downsample_factor)

            # Save if requested
            if request.save_path:
                point_cloud.save_ply(request.save_path)

            result = PointCloudResult(
                scanner_name=scanner_name,
                num_points=point_cloud.num_points,
                has_colors=point_cloud.has_colors,
                has_normals=point_cloud.has_normals if hasattr(point_cloud, "has_normals") else False,
                has_confidence=point_cloud.has_confidence if hasattr(point_cloud, "has_confidence") else False,
                saved_path=request.save_path,
                points_shape=point_cloud.points.shape if point_cloud.points is not None else None,
                colors_shape=point_cloud.colors.shape if point_cloud.colors is not None else None,
                capture_timestamp=datetime.now(timezone.utc).isoformat(),
            )

            return PointCloudResponse(success=True, message="Point cloud captured", data=result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def capture_point_cloud_batch(self, request: PointCloudCaptureBatchRequest) -> PointCloudBatchResponse:
        """Capture point clouds from multiple scanners."""
        results = []
        successful = 0
        failed = 0
        errors = {}

        for capture_config in request.captures:
            scanner_name = capture_config.get("scanner")
            try:
                if not scanner_name:
                    raise ValueError("Scanner name required")

                if scanner_name not in self._scanners:
                    raise CameraNotFoundError(f"Scanner {scanner_name} not found")

                scanner = self._scanners[scanner_name]

                point_cloud = await scanner.capture_point_cloud(
                    include_colors=capture_config.get("include_colors", True),
                    include_confidence=capture_config.get("include_confidence", False),
                )

                self._total_point_clouds += 1

                result = PointCloudResult(
                    scanner_name=scanner_name,
                    num_points=point_cloud.num_points,
                    has_colors=point_cloud.has_colors,
                    capture_timestamp=datetime.now(timezone.utc).isoformat(),
                )

                results.append(result)
                successful += 1
            except Exception as e:
                failed += 1
                errors[scanner_name or "unknown"] = str(e)

        batch_result = PointCloudBatchResult(successful=successful, failed=failed, results=results, errors=errors)

        return PointCloudBatchResponse(
            success=failed == 0,
            message=f"Captured {successful}/{len(request.captures)} point clouds",
            data=batch_result,
        )
