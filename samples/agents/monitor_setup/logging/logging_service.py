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




class LoggingService(Service):
    """
    A Logging Service that simulates industrial automation logging patterns.
    
    Generates realistic logs including:
    - Scan triggers and completions
    - Capture operations with timing
    - Timeout errors
    - Connection issues
    - Defect detection results
    """
    
    def __init__(
        self,
        error_rate: float = 0.1,  # 10% error rate
        timeout_rate: float = 0.05,  # 5% timeout rate
        auto_scan_interval: float = 5.0,  # Auto-scan every 5 seconds
        use_structlog: bool = True,
        **kwargs
    ):
        kwargs["use_structlog"] = use_structlog
        super().__init__(**kwargs)
        
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
        
        # Override the FastAPI lifespan to include background task startup
        self._setup_lifespan()
        
        self.logger.info(
            "logging_service_initialized",
            error_rate=self.error_rate,
            timeout_rate=self.timeout_rate,
            auto_scan_interval=self.auto_scan_interval,
        )

    def _setup_lifespan(self):
        """Setup custom lifespan for background scan loop."""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        
        @asynccontextmanager
        async def logging_lifespan(app: FastAPI):
            """Custom lifespan that includes background scan loop startup."""
            # Start background scan loop
            await self._on_startup()
            yield
            # Shutdown background scan loop
            await self._on_shutdown()
            # Ensure parent's shutdown cleanup is called
            await self.shutdown_cleanup()
        
        # Replace the app's lifespan
        self.app.router.lifespan_context = logging_lifespan

    async def _on_startup(self):
        """Start background scanning task."""
        self.logger.info(
            "logging_service_startup",
            status="initializing",
            timestamp=datetime.now().isoformat(),
        )
        self._background_task = asyncio.create_task(self._background_scan_loop())
        self.logger.info("background_task_started", task="auto_scan_loop")

    async def _on_shutdown(self):
        """Stop background scanning task."""
        self.logger.info("logging_service_shutdown", status="stopping")
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                self.logger.info("background_task_cancelled")

    # ─────────────────────────────────────────────────────────────────────────
    # Background Task - Simulates continuous logging
    # ─────────────────────────────────────────────────────────────────────────

    async def _background_scan_loop(self):
        """Continuous background loop that simulates logging operations."""
        self.logger.info(
            "background_task_loop_started",
            interval=self.auto_scan_interval,
        )
        
        scan_cycle = 0
        while True:
            try:
                scan_cycle += 1
                
                sn = f"SN{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
                part_number = f"PART-{random.choice(['A1', 'B2', 'C3', 'D4'])}-{random.randint(1000, 9999)}"
                
                self.logger.info(
                    "part_detected",
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
                serial_number=serial_number,
                defect_status=defect_status,
                part_status="Defective" if is_defective else "Healthy",
                inference_time_ms=int(inference_time * 1000),
            )
            
            if is_defective:
                self.logger.warning(
                    "defect_detected",
                    request_id=request_id,
                    serial_number=serial_number,
                    part_number=part_number,
                    defect_code=defect_status,
                    scan_type=scan_type.value,
                )
            
            # Acknowledge completion
            self.logger.info(
                f"{scan_type.value.lower()}_scan_acknowledged",
                request_id=request_id,
                status="success",
            )
            
            self.successful_scans += 1
            return True
            
        except Exception as e:
            self.logger.error(
                f"{scan_type.value.lower()}_scan_exception",
                request_id=request_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            self.failed_scans += 1
            return False
        finally:
            self.active_scans -= 1






