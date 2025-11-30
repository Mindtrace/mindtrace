"""
PLCManagerService - Service-based API for PLC management.

This service wraps PLCManager functionality in a Service-based
architecture with comprehensive MCP tool integration and typed client access.
"""

import time
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware

from mindtrace.hardware.api.plcs.models import (
    # Response models
    ActivePLCsResponse,
    BackendInfo,
    BackendInfoResponse,
    BackendsResponse,
    BatchOperationResponse,
    BatchOperationResult,
    BatchTagReadResponse,
    BatchTagWriteResponse,
    BoolResponse,
    ListResponse,
    PLCConnectBatchRequest,
    PLCConnectRequest,
    PLCDisconnectBatchRequest,
    PLCDisconnectRequest,
    PLCInfo,
    PLCInfoResponse,
    PLCQueryRequest,
    PLCStatus,
    PLCStatusResponse,
    SystemDiagnostics,
    SystemDiagnosticsResponse,
    TagBatchReadRequest,
    TagBatchWriteRequest,
    TagInfo,
    TagInfoRequest,
    TagInfoResponse,
    TagListResponse,
    TagReadRequest,
    TagReadResponse,
    TagWriteRequest,
    TagWriteResponse,
)
from mindtrace.hardware.api.plcs.models.requests import BackendFilterRequest
from mindtrace.hardware.api.plcs.schemas import ALL_SCHEMAS
from mindtrace.hardware.core.exceptions import PLCNotFoundError
from mindtrace.hardware.plcs.plc_manager import PLCManager
from mindtrace.services import Service


class PLCManagerService(Service):
    """
    PLC Management Service.

    Provides comprehensive PLC management functionality through a Service-based
    architecture with MCP tool integration and async PLC operations.
    """

    def __init__(self, **kwargs):
        """Initialize PLCManagerService.

        Args:
            **kwargs: Additional Service initialization parameters
        """
        super().__init__(
            summary="PLC Management Service",
            description="REST API and MCP tools for comprehensive PLC management and control",
            **kwargs,
        )

        # Enable CORS for cross-origin requests from frontend
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._plc_manager: Optional[PLCManager] = None
        self._startup_time = time.time()

        # Statistics tracking
        self._total_tag_reads = 0
        self._total_tag_writes = 0

        # Register all endpoints with their schemas
        self._register_endpoints()

    async def _get_plc_manager(self) -> PLCManager:
        """Get or create PLC manager instance."""
        self.logger.debug(f"_get_plc_manager called, current manager: {self._plc_manager}")
        if self._plc_manager is None:
            self.logger.debug("Creating new PLCManager")
            self._plc_manager = PLCManager()
            self.logger.debug("PLCManager initialization completed")
        self.logger.debug("Returning PLC manager")
        return self._plc_manager

    async def shutdown_cleanup(self):
        """Cleanup PLC manager on shutdown."""
        if self._plc_manager is not None:
            try:
                await self._plc_manager.cleanup()
            except Exception as e:
                self.logger.error(f"Error closing PLC manager: {e}")
            finally:
                self._plc_manager = None
        await super().shutdown_cleanup()

    def _register_endpoints(self):
        """Register all service endpoints."""
        # Backend & Discovery
        self.add_endpoint(
            "plcs/backends", self.discover_backends, ALL_SCHEMAS["discover_backends"], methods=["GET"], as_tool=True
        )
        self.add_endpoint(
            "plcs/backends/info", self.get_backend_info, ALL_SCHEMAS["get_backend_info"], methods=["GET"], as_tool=True
        )
        self.add_endpoint("plcs/discover", self.discover_plcs, ALL_SCHEMAS["discover_plcs"], as_tool=True)

        # PLC Lifecycle
        self.add_endpoint("plcs/connect", self.connect_plc, ALL_SCHEMAS["connect_plc"], as_tool=True)
        self.add_endpoint(
            "plcs/connect/batch", self.connect_plcs_batch, ALL_SCHEMAS["connect_plcs_batch"], as_tool=True
        )
        self.add_endpoint("plcs/disconnect", self.disconnect_plc, ALL_SCHEMAS["disconnect_plc"], as_tool=True)
        self.add_endpoint(
            "plcs/disconnect/batch", self.disconnect_plcs_batch, ALL_SCHEMAS["disconnect_plcs_batch"], as_tool=True
        )
        self.add_endpoint(
            "plcs/disconnect/all", self.disconnect_all_plcs, ALL_SCHEMAS["disconnect_all_plcs"], as_tool=True
        )
        self.add_endpoint(
            "plcs/active", self.get_active_plcs, ALL_SCHEMAS["get_active_plcs"], methods=["GET"], as_tool=True
        )

        # Tag Operations
        self.add_endpoint("plcs/tags/read", self.read_tags, ALL_SCHEMAS["tag_read"], as_tool=True)
        self.add_endpoint("plcs/tags/write", self.write_tags, ALL_SCHEMAS["tag_write"], as_tool=True)
        self.add_endpoint("plcs/tags/read/batch", self.read_tags_batch, ALL_SCHEMAS["tag_batch_read"], as_tool=True)
        self.add_endpoint("plcs/tags/write/batch", self.write_tags_batch, ALL_SCHEMAS["tag_batch_write"], as_tool=True)
        self.add_endpoint("plcs/tags/list", self.list_tags, ALL_SCHEMAS["tag_list"], as_tool=True)
        self.add_endpoint("plcs/tags/info", self.get_tag_info, ALL_SCHEMAS["tag_info"], as_tool=True)

        # Status & Information
        self.add_endpoint("plcs/status", self.get_plc_status, ALL_SCHEMAS["get_plc_status"], as_tool=True)
        self.add_endpoint("plcs/info", self.get_plc_info, ALL_SCHEMAS["get_plc_info"], as_tool=True)
        self.add_endpoint(
            "system/diagnostics",
            self.get_system_diagnostics,
            ALL_SCHEMAS["get_system_diagnostics"],
            methods=["GET"],
            as_tool=True,
        )

    # Backend & Discovery Operations
    async def discover_backends(self) -> BackendsResponse:
        """Discover available PLC backends."""
        try:
            manager = await self._get_plc_manager()
            backend_info = manager.get_backend_info()
            backends = list(backend_info.keys())

            return BackendsResponse(success=True, message=f"Found {len(backends)} available backends", data=backends)
        except Exception as e:
            self.logger.error(f"Backend discovery failed: {e}")
            raise

    async def get_backend_info(self) -> BackendInfoResponse:
        """Get detailed information about all backends."""
        try:
            manager = await self._get_plc_manager()
            backend_info = manager.get_backend_info()

            # Convert to BackendInfo models
            backend_models = {}
            for name, info in backend_info.items():
                backend_models[name] = BackendInfo(
                    name=name,
                    available=info.get("sdk_available", info.get("available", True)),
                    type="hardware",
                    sdk_required=True,
                    description=info.get("description", f"{name} PLC backend"),
                    sdk_name=info.get("sdk_name"),
                    drivers=info.get("drivers"),
                )

            return BackendInfoResponse(
                success=True, message=f"Retrieved information for {len(backend_models)} backends", data=backend_models
            )
        except Exception as e:
            self.logger.error(f"Backend info retrieval failed: {e}")
            raise

    async def discover_plcs(self, request: BackendFilterRequest) -> ListResponse:
        """Discover available PLCs from all or specific backends."""
        try:
            manager = await self._get_plc_manager()
            discovered_plcs = await manager.discover_plcs()

            # Flatten discovered PLCs
            all_plcs = []
            for backend_name, plc_list in discovered_plcs.items():
                if request.backend is None or backend_name == request.backend:
                    all_plcs.extend(plc_list)

            return ListResponse(
                success=True,
                message=f"Found {len(all_plcs)} PLCs"
                + (f" from backend '{request.backend}'" if request.backend else " from all backends"),
                data=all_plcs,
            )
        except Exception as e:
            self.logger.error(f"PLC discovery failed: {e}")
            raise

    # PLC Lifecycle Operations
    async def connect_plc(self, request: PLCConnectRequest) -> BoolResponse:
        """Connect to a PLC."""
        try:
            manager = await self._get_plc_manager()

            # Register PLC
            await manager.register_plc(
                plc_name=request.plc_name,
                backend=request.backend,
                ip_address=request.ip_address,
                plc_type=request.plc_type,
                connection_timeout=request.connection_timeout,
                read_timeout=request.read_timeout,
                write_timeout=request.write_timeout,
                retry_count=request.retry_count,
                retry_delay=request.retry_delay,
            )

            # Connect to PLC
            success = await manager.connect_plc(request.plc_name)

            return BoolResponse(
                success=success, message=f"PLC '{request.plc_name}' connected successfully", data=success
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to PLC '{request.plc_name}': {e}")
            raise

    async def connect_plcs_batch(self, request: PLCConnectBatchRequest) -> BatchOperationResponse:
        """Connect to multiple PLCs in batch."""
        try:
            manager = await self._get_plc_manager()
            successful = []
            failed = []
            results = {}

            for plc_req in request.plcs:
                try:
                    # Register PLC
                    await manager.register_plc(
                        plc_name=plc_req.plc_name,
                        backend=plc_req.backend,
                        ip_address=plc_req.ip_address,
                        plc_type=plc_req.plc_type,
                        connection_timeout=plc_req.connection_timeout,
                        read_timeout=plc_req.read_timeout,
                        write_timeout=plc_req.write_timeout,
                        retry_count=plc_req.retry_count,
                        retry_delay=plc_req.retry_delay,
                    )

                    # Connect to PLC
                    success = await manager.connect_plc(plc_req.plc_name)
                    if success:
                        successful.append(plc_req.plc_name)
                        results[plc_req.plc_name] = True
                    else:
                        failed.append(plc_req.plc_name)
                        results[plc_req.plc_name] = False
                except Exception as e:
                    self.logger.warning(f"Failed to connect to PLC '{plc_req.plc_name}': {e}")
                    failed.append(plc_req.plc_name)
                    results[plc_req.plc_name] = False

            result = BatchOperationResult(
                successful=successful,
                failed=failed,
                results=results,
                successful_count=len(successful),
                failed_count=len(failed),
            )

            return BatchOperationResponse(
                success=len(failed) == 0,
                message=f"Batch connect completed: {len(successful)} successful, {len(failed)} failed",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Batch PLC connection failed: {e}")
            raise

    async def disconnect_plc(self, request: PLCDisconnectRequest) -> BoolResponse:
        """Disconnect from a PLC."""
        try:
            manager = await self._get_plc_manager()
            success = await manager.disconnect_plc(request.plc)

            return BoolResponse(success=success, message=f"PLC '{request.plc}' disconnected successfully", data=success)
        except Exception as e:
            self.logger.error(f"Failed to disconnect from PLC '{request.plc}': {e}")
            raise

    async def disconnect_plcs_batch(self, request: PLCDisconnectBatchRequest) -> BatchOperationResponse:
        """Disconnect from multiple PLCs in batch."""
        try:
            manager = await self._get_plc_manager()
            results = await manager.disconnect_all_plcs()

            # Filter to requested PLCs only
            filtered_results = {plc: results.get(plc, False) for plc in request.plcs}
            successful = [plc for plc, success in filtered_results.items() if success]
            failed = [plc for plc, success in filtered_results.items() if not success]

            result = BatchOperationResult(
                successful=successful,
                failed=failed,
                results=filtered_results,
                successful_count=len(successful),
                failed_count=len(failed),
            )

            return BatchOperationResponse(
                success=len(failed) == 0,
                message=f"Batch disconnect completed: {len(successful)} successful, {len(failed)} failed",
                data=result,
            )
        except Exception as e:
            self.logger.error(f"Batch PLC disconnection failed: {e}")
            raise

    async def disconnect_all_plcs(self) -> BoolResponse:
        """Disconnect from all active PLCs."""
        try:
            manager = await self._get_plc_manager()
            results = await manager.disconnect_all_plcs()
            plc_count = len(results)

            return BoolResponse(success=True, message=f"Successfully disconnected {plc_count} PLCs", data=True)
        except Exception as e:
            self.logger.error(f"Failed to disconnect all PLCs: {e}")
            raise

    async def get_active_plcs(self) -> ActivePLCsResponse:
        """Get list of currently active PLCs."""
        try:
            manager = await self._get_plc_manager()
            active_plcs = manager.get_registered_plcs()

            return ActivePLCsResponse(success=True, message=f"Found {len(active_plcs)} active PLCs", data=active_plcs)
        except Exception as e:
            self.logger.error(f"Failed to get active PLCs: {e}")
            raise

    # Tag Operations
    async def read_tags(self, request: TagReadRequest) -> TagReadResponse:
        """Read tag values from a PLC."""
        try:
            manager = await self._get_plc_manager()
            values = await manager.read_tag(request.plc, request.tags)

            self._total_tag_reads += len(values) if isinstance(values, dict) else 1

            tag_count = len(values) if isinstance(values, dict) else 1
            return TagReadResponse(success=True, message=f"Read {tag_count} tags from PLC '{request.plc}'", data=values)
        except Exception as e:
            self.logger.error(f"Failed to read tags from PLC '{request.plc}': {e}")
            raise

    async def write_tags(self, request: TagWriteRequest) -> TagWriteResponse:
        """Write tag values to a PLC."""
        try:
            manager = await self._get_plc_manager()
            results = await manager.write_tag(request.plc, request.tags)

            self._total_tag_writes += len(results) if isinstance(results, dict) else 1

            tag_count = len(results) if isinstance(results, dict) else 1
            return TagWriteResponse(
                success=True, message=f"Wrote {tag_count} tags to PLC '{request.plc}'", data=results
            )
        except Exception as e:
            self.logger.error(f"Failed to write tags to PLC '{request.plc}': {e}")
            raise

    async def read_tags_batch(self, request: TagBatchReadRequest) -> BatchTagReadResponse:
        """Read tags from multiple PLCs in batch."""
        try:
            manager = await self._get_plc_manager()
            results = await manager.read_tags_batch(request.requests)

            successful_count = sum(1 for v in results.values() if not isinstance(v, dict) or "error" not in v)
            failed_count = len(results) - successful_count

            return BatchTagReadResponse(
                success=successful_count > 0,
                message=f"Batch read completed: {successful_count} successful, {failed_count} failed",
                data=results,
                successful_count=successful_count,
                failed_count=failed_count,
            )
        except Exception as e:
            self.logger.error(f"Batch tag read failed: {e}")
            raise

    async def write_tags_batch(self, request: TagBatchWriteRequest) -> BatchTagWriteResponse:
        """Write tags to multiple PLCs in batch."""
        try:
            manager = await self._get_plc_manager()
            results = await manager.write_tags_batch(request.requests)

            successful_count = sum(1 for v in results.values() if not isinstance(v, dict) or "error" not in v)
            failed_count = len(results) - successful_count

            return BatchTagWriteResponse(
                success=successful_count > 0,
                message=f"Batch write completed: {successful_count} successful, {failed_count} failed",
                data=results,
                successful_count=successful_count,
                failed_count=failed_count,
            )
        except Exception as e:
            self.logger.error(f"Batch tag write failed: {e}")
            raise

    async def list_tags(self, request: PLCQueryRequest) -> TagListResponse:
        """List all available tags on a PLC."""
        try:
            manager = await self._get_plc_manager()
            tags = await manager.get_plc_tags(request.plc)

            return TagListResponse(success=True, message=f"Found {len(tags)} tags on PLC '{request.plc}'", data=tags)
        except Exception as e:
            self.logger.error(f"Failed to list tags for PLC '{request.plc}': {e}")
            raise

    async def get_tag_info(self, request: TagInfoRequest) -> TagInfoResponse:
        """Get detailed information about a specific tag."""
        try:
            manager = await self._get_plc_manager()

            # Check if PLC is registered
            if request.plc not in manager.get_registered_plcs():
                raise PLCNotFoundError(f"PLC '{request.plc}' is not registered")

            # Get tag info from the PLC
            plc_instance = manager.plcs[request.plc]
            tag_info_dict = await plc_instance.get_tag_info(request.tag)

            tag_info = TagInfo(
                name=tag_info_dict.get("name", request.tag),
                type=tag_info_dict.get("type", "Unknown"),
                description=tag_info_dict.get("description"),
                size=tag_info_dict.get("size", 0),
                driver=tag_info_dict.get("driver"),
            )

            return TagInfoResponse(
                success=True, message=f"Retrieved information for tag '{request.tag}'", data=tag_info
            )
        except Exception as e:
            self.logger.error(f"Failed to get tag info for '{request.tag}' on PLC '{request.plc}': {e}")
            raise

    # Status & Information Operations
    async def get_plc_status(self, request: PLCQueryRequest) -> PLCStatusResponse:
        """Get PLC status information."""
        try:
            manager = await self._get_plc_manager()
            status_dict = await manager.get_plc_status(request.plc)

            status = PLCStatus(
                plc=request.plc,
                connected=status_dict.get("connected", False),
                initialized=status_dict.get("initialized", False),
                backend=status_dict.get("backend", "Unknown"),
                ip_address=status_dict.get("ip_address", ""),
                plc_type=status_dict.get("plc_type"),
                driver_type=status_dict.get("driver_type"),
                error_count=0,
            )

            return PLCStatusResponse(success=True, message=f"Retrieved status for PLC '{request.plc}'", data=status)
        except Exception as e:
            self.logger.error(f"Failed to get PLC status for '{request.plc}': {e}")
            raise

    async def get_plc_info(self, request: PLCQueryRequest) -> PLCInfoResponse:
        """Get detailed PLC information."""
        try:
            manager = await self._get_plc_manager()
            status_dict = await manager.get_plc_status(request.plc)

            info = PLCInfo(
                name=request.plc,
                backend=status_dict.get("backend", "Unknown"),
                ip_address=status_dict.get("ip_address", ""),
                plc_type=status_dict.get("plc_type"),
                active=True,
                connected=status_dict.get("connected", False),
                driver_type=status_dict.get("driver_type"),
                product_name=status_dict.get("product_name"),
                product_type=status_dict.get("product_type"),
                vendor=status_dict.get("vendor"),
                revision=status_dict.get("revision"),
                serial=status_dict.get("serial"),
            )

            return PLCInfoResponse(success=True, message=f"Retrieved information for PLC '{request.plc}'", data=info)
        except Exception as e:
            self.logger.error(f"Failed to get PLC info for '{request.plc}': {e}")
            raise

    # System Diagnostics
    async def get_system_diagnostics(self) -> SystemDiagnosticsResponse:
        """Get system diagnostics information."""
        try:
            manager = await self._get_plc_manager()
            all_status = await manager.get_all_plc_status()

            active_plcs = len(all_status)
            connected_plcs = sum(1 for status in all_status.values() if status.get("connected", False))

            # Get backend status
            backend_info = manager.get_backend_info()
            backend_status = {name: info.get("sdk_available", True) for name, info in backend_info.items()}

            uptime_seconds = time.time() - self._startup_time

            diagnostics = SystemDiagnostics(
                active_plcs=active_plcs,
                connected_plcs=connected_plcs,
                backend_status=backend_status,
                uptime_seconds=uptime_seconds,
                total_tag_reads=self._total_tag_reads,
                total_tag_writes=self._total_tag_writes,
            )

            return SystemDiagnosticsResponse(
                success=True, message="System diagnostics retrieved successfully", data=diagnostics
            )
        except Exception as e:
            self.logger.error(f"Failed to get system diagnostics: {e}")
            raise

    # Health Check
    async def health_check(self) -> dict:
        """Health check endpoint for container healthcheck."""
        try:
            manager = await self._get_plc_manager()
            backend_info = manager.get_backend_info()
            backends = list(backend_info.keys())
            active_plcs = manager.get_registered_plcs()

            return {
                "status": "healthy",
                "service": "plc-manager",
                "backends": backends,
                "active_plcs": len(active_plcs),
                "uptime_seconds": time.time() - self._startup_time,
            }
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "service": "plc-manager",
                "error": str(e),
            }
