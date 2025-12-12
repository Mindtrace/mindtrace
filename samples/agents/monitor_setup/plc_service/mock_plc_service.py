"""
MockPLC Service - Simulates a PLC service with realistic log patterns for testing monitoring agents.

This service mimics a real PLC controller that:
- Runs periodic scan cycles (static, robot vision, thread check)
- Generates various log levels (INFO, WARNING, ERROR)
- Simulates capture operations, timeouts, and defect detection
- Produces structured logs suitable for Loki/Grafana ingestion
"""

import asyncio
import random
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class ScanType(str, Enum):
    STATIC = "STATIC"
    ROBOT_VISION = "ROBOT_VISION"
    THREAD_CHECK = "THREAD_CHECK"


class TriggerInput(BaseModel):
    scan_type: ScanType
    serial_number: Optional[str] = None
    part_number: Optional[str] = None
    simulate_error: bool = False


class TriggerOutput(BaseModel):
    request_id: str
    status: str
    message: str


class StatusOutput(BaseModel):
    service_name: str
    uptime_seconds: float
    total_scans: int
    successful_scans: int
    failed_scans: int
    active_scans: int


class DefectResult(BaseModel):
    request_id: str
    part_status: str  # "Healthy" or "Defective"
    defect_code: Optional[int] = None


# Task schemas
trigger_scan_task = TaskSchema(name="trigger_scan", input_schema=TriggerInput, output_schema=TriggerOutput)
get_status_task = TaskSchema(name="get_status", input_schema=None, output_schema=StatusOutput)
submit_result_task = TaskSchema(name="submit_ml_result", input_schema=DefectResult, output_schema=TriggerOutput)


# ─────────────────────────────────────────────────────────────────────────────
# Mock PLC Service
# ─────────────────────────────────────────────────────────────────────────────

class MockPLCService(Service):
    """
    A mock PLC service that simulates industrial automation logging patterns.
    
    Generates realistic logs including:
    - Scan triggers and completions
    - Capture operations with timing
    - Timeout errors
    - Connection issues
    - Defect detection results
    """
    
    def __init__(
        self,
        plc_id: str = "PLC_001",
        error_rate: float = 0.1,  # 10% error rate
        timeout_rate: float = 0.05,  # 5% timeout rate
        auto_scan_interval: float = 5.0,  # Auto-scan every 5 seconds
        use_structlog: bool = True,
        **kwargs
    ):
        kwargs["use_structlog"] = use_structlog
        super().__init__(**kwargs)
        
        self.plc_id = plc_id
        self.error_rate = error_rate
        self.timeout_rate = timeout_rate
        self.auto_scan_interval = auto_scan_interval
        
        # Statistics
        self.start_time = datetime.now()
        self.total_scans = 0
        self.successful_scans = 0
        self.failed_scans = 0
        self.active_scans = 0
        
        # Background task handle
        self._background_task: Optional[asyncio.Task] = None
        
        # Add middleware for request logging
        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )
        
        # Register endpoints
        self.add_endpoint("trigger_scan", self.trigger_scan, schema=trigger_scan_task)
        self.add_endpoint("status", self.get_status, schema=get_status_task, methods=["GET"])
        self.add_endpoint("ml_response", self.receive_ml_response, schema=submit_result_task)
        
        # Register lifecycle hooks
        self.app.add_event_handler("startup", self._on_startup)
        self.app.add_event_handler("shutdown", self._on_shutdown)
        
        self.logger.info(
            "mock_plc_service_initialized",
            plc_id=self.plc_id,
            error_rate=self.error_rate,
            timeout_rate=self.timeout_rate,
            auto_scan_interval=self.auto_scan_interval,
        )

    async def _on_startup(self):
        """Start background scanning task."""
        self.logger.info(
            "plc_service_startup",
            status="initializing",
            plc_id=self.plc_id,
            timestamp=datetime.now().isoformat(),
        )
        self._background_task = asyncio.create_task(self._background_scan_loop())
        self.logger.info("background_task_started", task="auto_scan_loop")

    async def _on_shutdown(self):
        """Stop background scanning task."""
        self.logger.info("plc_service_shutdown", status="stopping")
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                self.logger.info("background_task_cancelled")

    # ─────────────────────────────────────────────────────────────────────────
    # Background Task - Simulates continuous PLC monitoring
    # ─────────────────────────────────────────────────────────────────────────

    async def _background_scan_loop(self):
        """Continuous background loop that simulates PLC scan triggers."""
        self.logger.info(
            "background_task_loop_started",
            plc_id=self.plc_id,
            interval=self.auto_scan_interval,
        )
        
        scan_cycle = 0
        while True:
            try:
                scan_cycle += 1
                
                # Generate a mock serial number
                sn = f"SN{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
                part_number = f"PART-{random.choice(['A1', 'B2', 'C3', 'D4'])}-{random.randint(1000, 9999)}"
                
                self.logger.info(
                    "part_detected",
                    plc_id=self.plc_id,
                    serial_number=sn,
                    part_number=part_number,
                    scan_cycle=scan_cycle,
                )
                
                # Simulate checking triggers
                static_trigger = random.random() > 0.3
                robot_trigger = random.random() > 0.5
                thread_trigger = random.random() > 0.6
                
                self.logger.debug(
                    "trigger_status_check",
                    static_trigger=static_trigger,
                    robot_trigger=robot_trigger,
                    thread_trigger=thread_trigger,
                )
                
                # Run scans based on triggers
                if static_trigger:
                    await self._run_scan(ScanType.STATIC, sn, part_number)
                
                if robot_trigger:
                    await self._run_scan(ScanType.ROBOT_VISION, sn, part_number)
                
                if thread_trigger:
                    await self._run_scan(ScanType.THREAD_CHECK, sn, part_number)
                
                await asyncio.sleep(self.auto_scan_interval)
                
            except asyncio.CancelledError:
                self.logger.info("background_loop_cancelled")
                break
            except Exception as e:
                self.logger.error(
                    "background_task_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    plc_id=self.plc_id,
                )
                await asyncio.sleep(5)  # Wait before retrying

    # ─────────────────────────────────────────────────────────────────────────
    # Scan Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_scan(
        self,
        scan_type: ScanType,
        serial_number: str,
        part_number: str,
        simulate_error: bool = False,
    ) -> bool:
        """Execute a scan operation with realistic logging."""
        request_id = f"{serial_number}_{scan_type.value}_{uuid.uuid4().hex[:8]}"
        
        self.active_scans += 1
        self.total_scans += 1
        
        self.logger.info(
            f"{scan_type.value.lower()}_scan_started",
            request_id=request_id,
            plc_id=self.plc_id,
            serial_number=serial_number,
            part_number=part_number,
            scan_type=scan_type.value,
        )
        
        try:
            # Simulate pre-capture delay
            pre_capture_delay = random.uniform(0.1, 0.5)
            await asyncio.sleep(pre_capture_delay)
            
            # Check for simulated timeout
            if simulate_error or random.random() < self.timeout_rate:
                self.logger.error(
                    f"{scan_type.value.lower()}_capture_timeout",
                    request_id=request_id,
                    plc_id=self.plc_id,
                    serial_number=serial_number,
                    timeout_seconds=10,
                    error_code=502,
                )
                self.failed_scans += 1
                return False
            
            # Simulate capture operation
            self.logger.info(
                f"{scan_type.value.lower()}_capture_started",
                request_id=request_id,
                plc_id=self.plc_id,
                position_idx=random.randint(0, 16) if scan_type == ScanType.ROBOT_VISION else 0,
            )
            
            capture_time = random.uniform(0.2, 1.0)
            await asyncio.sleep(capture_time)
            
            # Check for random errors
            if random.random() < self.error_rate:
                error_type = random.choice([
                    "camera_connection_lost",
                    "plc_communication_error",
                    "image_capture_failed",
                    "tag_read_error",
                ])
                self.logger.error(
                    error_type,
                    request_id=request_id,
                    plc_id=self.plc_id,
                    serial_number=serial_number,
                    scan_type=scan_type.value,
                    error_code=random.choice([503, 504, 505]),
                )
                self.failed_scans += 1
                return False
            
            # Simulate capture success
            self.logger.info(
                f"{scan_type.value.lower()}_capture_complete",
                request_id=request_id,
                plc_id=self.plc_id,
                capture_time_ms=int(capture_time * 1000),
            )
            
            # Simulate inference delay
            inference_time = random.uniform(0.5, 2.0)
            await asyncio.sleep(inference_time)
            
            # Simulate defect detection result
            is_defective = random.random() < 0.15  # 15% defect rate
            defect_status = 1001 if is_defective else 1000
            
            self.logger.info(
                f"{scan_type.value.lower()}_inference_complete",
                request_id=request_id,
                plc_id=self.plc_id,
                serial_number=serial_number,
                defect_status=defect_status,
                part_status="Defective" if is_defective else "Healthy",
                inference_time_ms=int(inference_time * 1000),
            )
            
            if is_defective:
                self.logger.warning(
                    "defect_detected",
                    request_id=request_id,
                    plc_id=self.plc_id,
                    serial_number=serial_number,
                    part_number=part_number,
                    defect_code=defect_status,
                    scan_type=scan_type.value,
                )
            
            # Acknowledge completion
            self.logger.info(
                f"{scan_type.value.lower()}_scan_acknowledged",
                request_id=request_id,
                plc_id=self.plc_id,
                status="success",
            )
            
            self.successful_scans += 1
            return True
            
        except Exception as e:
            self.logger.error(
                f"{scan_type.value.lower()}_scan_exception",
                request_id=request_id,
                plc_id=self.plc_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            self.failed_scans += 1
            return False
        finally:
            self.active_scans -= 1

    # ─────────────────────────────────────────────────────────────────────────
    # Endpoints
    # ─────────────────────────────────────────────────────────────────────────

    async def trigger_scan(self, payload: TriggerInput) -> TriggerOutput:
        """Manually trigger a scan operation."""
        serial_number = payload.serial_number or f"SN{datetime.now().strftime('%Y%m%d%H%M%S')}"
        part_number = payload.part_number or f"PART-MANUAL-{random.randint(1000, 9999)}"
        
        self.logger.info(
            "manual_scan_triggered",
            scan_type=payload.scan_type.value,
            serial_number=serial_number,
            simulate_error=payload.simulate_error,
        )
        
        # Run the scan in background
        asyncio.create_task(
            self._run_scan(
                payload.scan_type,
                serial_number,
                part_number,
                payload.simulate_error,
            )
        )
        
        return TriggerOutput(
            request_id=f"{serial_number}_{payload.scan_type.value}",
            status="triggered",
            message=f"{payload.scan_type.value} scan triggered for {serial_number}",
        )

    async def get_status(self) -> StatusOutput:
        """Get service status and statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return StatusOutput(
            service_name=self.name,
            uptime_seconds=uptime,
            total_scans=self.total_scans,
            successful_scans=self.successful_scans,
            failed_scans=self.failed_scans,
            active_scans=self.active_scans,
        )

    async def receive_ml_response(self, payload: DefectResult) -> TriggerOutput:
        """Receive ML inference result (simulates callback from ML service)."""
        self.logger.info(
            "ml_response_received",
            request_id=payload.request_id,
            part_status=payload.part_status,
            defect_code=payload.defect_code,
        )
        
        return TriggerOutput(
            request_id=payload.request_id,
            status="acknowledged",
            message=f"ML result for {payload.request_id}: {payload.part_status}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Launch
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Mock PLC Service for testing")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--plc-id", default="PLC_001", help="PLC identifier")
    parser.add_argument("--error-rate", type=float, default=0.1, help="Error rate (0-1)")
    parser.add_argument("--scan-interval", type=float, default=5.0, help="Auto-scan interval in seconds")
    args = parser.parse_args()
    
    service = MockPLCService(
        plc_id=args.plc_id,
        error_rate=args.error_rate,
        auto_scan_interval=args.scan_interval,
    )
    
    service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,
        timeout=100,
    )

