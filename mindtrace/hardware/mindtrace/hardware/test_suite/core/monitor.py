"""
Hardware test monitoring and metrics collection.

Tracks operation results and provides summary statistics.
"""

import time
from dataclasses import dataclass
from typing import Optional

from mindtrace.core import Mindtrace


@dataclass
class TestSummary:
    """Summary of test execution."""

    scenario_name: str
    duration: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    timeout_operations: int
    success_rate: float
    average_operation_time: float
    max_operation_time: float
    min_operation_time: float
    operations_per_second: float
    top_errors: list = None  # For compatibility with display utils


class HardwareMonitor(Mindtrace):
    """
    Monitor for hardware test execution.

    Tracks basic metrics and provides summary reporting.
    """

    def __init__(self, scenario_name: str, **kwargs):
        """
        Initialize monitor for a scenario.

        Args:
            scenario_name: Name of the scenario being monitored
            **kwargs: Additional Mindtrace initialization parameters
        """
        super().__init__(**kwargs)

        self.scenario_name = scenario_name
        self.start_time = time.time()
        self.end_time: Optional[float] = None

        # Operation counters
        self.operations_total = 0
        self.operations_success = 0
        self.operations_failed = 0
        self.operations_timeout = 0

        # Timing metrics
        self.operation_times: list[float] = []

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

        if success:
            self.operations_success += 1
        else:
            self.operations_failed += 1

            # Check for timeout
            if error and ("timeout" in str(error).lower() or "Timeout" in type(error).__name__):
                self.operations_timeout += 1

        self.operation_times.append(duration)

    def finalize(self) -> None:
        """Mark monitoring as complete."""
        self.end_time = time.time()

    def get_duration(self) -> float:
        """Get test duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    def get_success_rate(self) -> float:
        """Get success rate as a decimal (0.0-1.0)."""
        if self.operations_total == 0:
            return 0.0
        return self.operations_success / self.operations_total

    def get_current_metrics(self) -> dict:
        """Get current real-time metrics (for runner compatibility)."""
        return {
            "operations_total": self.operations_total,
            "operations_success": self.operations_success,
            "operations_failed": self.operations_failed,
            "operations_timeout": self.operations_timeout,
            "success_rate": self.get_success_rate(),
        }

    def get_summary(self) -> TestSummary:
        """Get comprehensive summary (for runner compatibility)."""
        if self.end_time is None:
            self.finalize()

        duration = self.get_duration()
        success_rate = self.get_success_rate()

        # Calculate timing stats
        avg_time = sum(self.operation_times) / len(self.operation_times) if self.operation_times else 0.0
        min_time = min(self.operation_times) if self.operation_times else 0.0
        max_time = max(self.operation_times) if self.operation_times else 0.0
        ops_per_sec = self.operations_total / duration if duration > 0 else 0.0

        return TestSummary(
            scenario_name=self.scenario_name,
            duration=duration,
            total_operations=self.operations_total,
            successful_operations=self.operations_success,
            failed_operations=self.operations_failed,
            timeout_operations=self.operations_timeout,
            success_rate=success_rate,
            average_operation_time=avg_time,
            max_operation_time=max_time,
            min_operation_time=min_time,
            operations_per_second=ops_per_sec,
            top_errors=[],  # Simplified monitor doesn't track detailed errors
        )

    def print_summary(self) -> None:
        """Print summary to console."""
        if self.end_time is None:
            self.finalize()

        duration = self.get_duration()
        success_rate = self.get_success_rate()

        # Calculate timing stats
        avg_time = sum(self.operation_times) / len(self.operation_times) if self.operation_times else 0.0
        min_time = min(self.operation_times) if self.operation_times else 0.0
        max_time = max(self.operation_times) if self.operation_times else 0.0
        ops_per_sec = self.operations_total / duration if duration > 0 else 0.0

        print("\n" + "=" * 70)
        print(f"Test Summary: {self.scenario_name}")
        print("=" * 70)
        print(f"Duration: {duration:.2f}s")
        print(f"Operations: {self.operations_total} total")
        print(f"  [✓] Success: {self.operations_success} ({success_rate:.1%})")
        print(f"  [✗] Failed: {self.operations_failed}")
        print(f"  [~] Timeout: {self.operations_timeout}")
        print("\nPerformance:")
        print(f"  Avg time: {avg_time:.3f}s")
        print(f"  Min time: {min_time:.3f}s")
        print(f"  Max time: {max_time:.3f}s")
        print(f"  Ops/sec: {ops_per_sec:.2f}")
        print("=" * 70 + "\n")
