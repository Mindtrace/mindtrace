"""
Hardware test monitoring and metrics collection.

Tracks operation results, detects failures, and provides summary statistics.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class OperationMetric:
    """Metrics for a single operation execution."""

    operation_index: int
    action: str
    start_time: float
    end_time: float
    duration: float
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0
    payload_size: int = 0
    response_size: int = 0


@dataclass
class MetricsSummary:
    """Summary of test execution metrics."""

    scenario_name: str
    start_time: datetime
    end_time: datetime
    duration: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    timeout_operations: int
    success_rate: float
    average_operation_time: float
    max_operation_time: float
    min_operation_time: float
    error_types: Dict[str, int]
    top_errors: List[tuple]
    operations_per_second: float


class HardwareMonitor:
    """
    Monitor for hardware test execution.

    Tracks metrics, detects anomalies, and provides real-time feedback
    during test execution.
    """

    def __init__(self, scenario_name: str):
        """
        Initialize monitor for a scenario.

        Args:
            scenario_name: Name of the scenario being monitored
        """
        self.scenario_name = scenario_name
        self.start_time = time.time()
        self.end_time: Optional[float] = None

        # Metrics storage
        self.operations: List[OperationMetric] = []
        self.error_types: Dict[str, int] = defaultdict(int)
        self.operation_times: List[float] = []

        # Real-time tracking
        self.operations_total = 0
        self.operations_success = 0
        self.operations_failed = 0
        self.operations_timeout = 0

        # Device tracking
        self.devices_tested: set = set()
        self.devices_failed: set = set()
        self.devices_hung: set = set()

    def record_operation(
        self,
        operation_index: int,
        action: str,
        duration: float,
        success: bool,
        error: Optional[Exception] = None,
        retry_count: int = 0,
        device_name: Optional[str] = None,
    ) -> None:
        """
        Record the result of an operation.

        Args:
            operation_index: Index of operation in scenario
            action: Type of operation performed
            duration: Time taken to execute (seconds)
            success: Whether operation succeeded
            error: Exception if operation failed
            retry_count: Number of retries performed
            device_name: Name of device being tested (for device tracking)
        """
        self.operations_total += 1

        # Update counters
        if success:
            self.operations_success += 1
        else:
            self.operations_failed += 1

            # Track error types
            if error:
                error_type = type(error).__name__
                self.error_types[error_type] += 1

                # Check for timeout
                if "timeout" in str(error).lower() or "Timeout" in error_type:
                    self.operations_timeout += 1

                    # Track hung devices
                    if device_name:
                        self.devices_hung.add(device_name)

        # Track device
        if device_name:
            self.devices_tested.add(device_name)
            if not success:
                self.devices_failed.add(device_name)

        # Store operation metric
        end_time = time.time()
        metric = OperationMetric(
            operation_index=operation_index,
            action=action,
            start_time=end_time - duration,
            end_time=end_time,
            duration=duration,
            success=success,
            error=str(error) if error else None,
            error_type=type(error).__name__ if error else None,
            retry_count=retry_count,
        )
        self.operations.append(metric)
        self.operation_times.append(duration)

    def mark_device_hung(self, device_name: str, operation: str) -> None:
        """
        Mark a device as hung during an operation.

        Args:
            device_name: Name of the device
            operation: Operation that caused hang
        """
        self.devices_hung.add(device_name)

    def get_current_metrics(self) -> Dict[str, Any]:
        """
        Get current real-time metrics.

        Returns:
            Dictionary of current metrics
        """
        current_time = time.time()
        elapsed = current_time - self.start_time

        return {
            "scenario": self.scenario_name,
            "elapsed_time": elapsed,
            "operations_total": self.operations_total,
            "operations_success": self.operations_success,
            "operations_failed": self.operations_failed,
            "operations_timeout": self.operations_timeout,
            "success_rate": self.operations_success / max(self.operations_total, 1),
            "timeout_rate": self.operations_timeout / max(self.operations_total, 1),
            "devices_tested": len(self.devices_tested),
            "devices_failed": len(self.devices_failed),
            "devices_hung": len(self.devices_hung),
            "operations_per_second": self.operations_total / max(elapsed, 1),
        }

    def finalize(self) -> None:
        """Mark monitoring as complete."""
        self.end_time = time.time()

    def get_summary(self) -> MetricsSummary:
        """
        Get comprehensive summary of test execution.

        Returns:
            MetricsSummary object with all statistics
        """
        if self.end_time is None:
            self.finalize()

        duration = self.end_time - self.start_time
        success_rate = self.operations_success / max(self.operations_total, 1)

        # Calculate operation time statistics
        avg_time = sum(self.operation_times) / len(self.operation_times) if self.operation_times else 0.0
        max_time = max(self.operation_times) if self.operation_times else 0.0
        min_time = min(self.operation_times) if self.operation_times else 0.0

        # Get top errors
        top_errors = sorted(self.error_types.items(), key=lambda x: x[1], reverse=True)[:5]

        return MetricsSummary(
            scenario_name=self.scenario_name,
            start_time=datetime.fromtimestamp(self.start_time, tz=timezone.utc),
            end_time=datetime.fromtimestamp(self.end_time, tz=timezone.utc),
            duration=duration,
            total_operations=self.operations_total,
            successful_operations=self.operations_success,
            failed_operations=self.operations_failed,
            timeout_operations=self.operations_timeout,
            success_rate=success_rate,
            average_operation_time=avg_time,
            max_operation_time=max_time,
            min_operation_time=min_time,
            error_types=dict(self.error_types),
            top_errors=top_errors,
            operations_per_second=self.operations_total / max(duration, 1),
        )

    def print_summary(self) -> None:
        """Print formatted summary to console."""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print(f"Test Summary: {summary.scenario_name}")
        print("=" * 70)
        print(f"Duration: {summary.duration:.2f}s")
        print(f"Operations: {summary.total_operations} total")
        print(f"  ✅ Success: {summary.successful_operations} ({summary.success_rate:.1%})")
        print(f"  ❌ Failed: {summary.failed_operations}")
        print(f"  ⏱️  Timeout: {summary.timeout_operations}")
        print(f"\nPerformance:")
        print(f"  Avg time: {summary.average_operation_time:.3f}s")
        print(f"  Min time: {summary.min_operation_time:.3f}s")
        print(f"  Max time: {summary.max_operation_time:.3f}s")
        print(f"  Ops/sec: {summary.operations_per_second:.2f}")

        if self.devices_hung:
            print(f"\n⚠️  Hung Devices: {', '.join(sorted(self.devices_hung))}")

        if summary.top_errors:
            print(f"\n🔴 Top Errors:")
            for error_type, count in summary.top_errors:
                print(f"  {error_type}: {count}")

        print("=" * 70 + "\n")
