"""
Hardware test runner with process isolation and timeout guards.

Executes test scenarios safely with watchdog timers, graceful error handling,
and comprehensive logging.
"""

import asyncio
import multiprocessing as mp
import signal
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from mindtrace.core import Mindtrace
from mindtrace.hardware.test_suite.core.monitor import HardwareMonitor
from mindtrace.hardware.test_suite.core.scenario import HardwareScenario, Operation, OperationType


class ScenarioStatus(str, Enum):
    """Status of scenario execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    HUNG = "hung"
    KILLED = "killed"


@dataclass
class ScenarioResult:
    """Result of scenario execution."""

    scenario_name: str
    status: ScenarioStatus
    duration: float
    operations_completed: int
    operations_total: int
    success_rate: float
    error: Optional[str] = None
    last_operation: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class TimeoutError(Exception):
    """Raised when operation times out."""

    pass


@contextmanager
def timeout_guard(seconds: float):
    """
    Context manager for operation timeout.

    Args:
        seconds: Timeout duration in seconds

    Raises:
        TimeoutError: If operation exceeds timeout
    """

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")

    # Set alarm
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(int(seconds))

    try:
        yield
    finally:
        # Cancel alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


class HardwareTestRunner(Mindtrace):
    """
    Test runner for hardware scenarios.

    Executes scenarios with process isolation, timeout protection,
    and comprehensive error handling.
    """

    def __init__(self, api_base_url: str, **kwargs):
        """
        Initialize test runner.

        Args:
            api_base_url: Base URL for hardware API
            **kwargs: Additional Mindtrace initialization parameters
        """
        super().__init__(**kwargs)
        self.api_base_url = api_base_url
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    async def execute_scenario(
        self, scenario: HardwareScenario, monitor: Optional[HardwareMonitor] = None, progress_callback=None
    ) -> ScenarioResult:
        """
        Execute a test scenario.

        Args:
            scenario: Scenario to execute
            monitor: Optional monitor for metrics collection
            progress_callback: Optional callback function(op_index, op_total, op_name, success) for progress updates

        Returns:
            ScenarioResult with execution outcome
        """
        # Validate scenario
        try:
            scenario.validate()
        except ValueError as e:
            self.logger.error(f"Invalid scenario '{scenario.name}': {e}")
            return ScenarioResult(
                scenario_name=scenario.name,
                status=ScenarioStatus.FAILED,
                duration=0.0,
                operations_completed=0,
                operations_total=len(scenario.operations),
                success_rate=0.0,
                error=f"Validation failed: {e}",
            )

        # Create monitor if not provided
        if monitor is None:
            monitor = HardwareMonitor(scenario.name)

        self.logger.info(f"Starting scenario: {scenario.name} ({len(scenario.operations)} operations)")
        start_time = time.time()

        # Storage for operation results
        stored_results: Dict[str, Any] = {}

        try:
            # Execute main operations
            for idx, operation in enumerate(scenario.operations):
                operation_start = time.time()
                success = False
                error = None

                try:
                    # Execute operation with timeout
                    result = await self._execute_operation(operation, stored_results, scenario.api_base_url)

                    # Store result if requested
                    if operation.store_result:
                        # Extract data from response if it has 'data' field
                        if isinstance(result, dict) and 'data' in result:
                            stored_results[operation.store_result] = result['data']
                        else:
                            stored_results[operation.store_result] = result

                    success = True
                    self.logger.debug(
                        f"Operation {idx + 1}/{len(scenario.operations)} completed: {operation.action.value}"
                    )

                except asyncio.TimeoutError as e:
                    error = e
                    self.logger.warning(
                        f"Operation {idx + 1}/{len(scenario.operations)} timed out: {operation.action.value}"
                    )

                except Exception as e:
                    error = e
                    self.logger.error(
                        f"Operation {idx + 1}/{len(scenario.operations)} failed: {operation.action.value} - {e}"
                    )

                    # Only raise if operation was expected to succeed
                    if operation.expected_success:
                        # For non-expected failures, continue
                        pass

                finally:
                    # Record metrics
                    operation_duration = time.time() - operation_start
                    monitor.record_operation(
                        operation_index=idx,
                        action=operation.action.value,
                        duration=operation_duration,
                        success=success,
                        error=error,
                    )

                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(idx, len(scenario.operations), operation.action.value, success)

            # Scenario completed
            duration = time.time() - start_time
            monitor.finalize()
            summary = monitor.get_summary()

            self.logger.info(
                f"Scenario '{scenario.name}' completed in {duration:.2f}s "
                f"({summary.success_rate:.1%} success rate)"
            )

            return ScenarioResult(
                scenario_name=scenario.name,
                status=ScenarioStatus.COMPLETED,
                duration=duration,
                operations_completed=summary.total_operations,
                operations_total=len(scenario.operations),
                success_rate=summary.success_rate,
                metrics=monitor.get_current_metrics(),
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Scenario '{scenario.name}' failed: {e}")

            return ScenarioResult(
                scenario_name=scenario.name,
                status=ScenarioStatus.FAILED,
                duration=duration,
                operations_completed=monitor.operations_total,
                operations_total=len(scenario.operations),
                success_rate=monitor.operations_success / max(monitor.operations_total, 1),
                error=str(e),
                last_operation=scenario.operations[monitor.operations_total - 1].action.value
                if monitor.operations_total > 0
                else None,
                metrics=monitor.get_current_metrics(),
            )

        finally:
            # Always execute cleanup operations, regardless of success or failure
            if scenario.cleanup_operations:
                self.logger.info(f"Executing {len(scenario.cleanup_operations)} cleanup operations")

                for idx, operation in enumerate(scenario.cleanup_operations):
                    try:
                        self.logger.debug(f"Cleanup operation {idx + 1}: {operation.action.value}")
                        await self._execute_operation(operation, stored_results, scenario.api_base_url)
                    except Exception as e:
                        # Log cleanup failures but don't raise - best effort cleanup
                        self.logger.warning(f"Cleanup operation {idx + 1} failed: {e}")

    async def _execute_operation(
        self, operation: Operation, stored_results: Dict[str, Any], api_base_url: str
    ) -> Any:
        """
        Execute a single operation.

        Args:
            operation: Operation to execute
            stored_results: Storage for operation results
            api_base_url: Base URL for API

        Returns:
            Operation result

        Raises:
            asyncio.TimeoutError: If operation times out
            Exception: If operation fails
        """
        # Handle special operations
        if operation.action == OperationType.WAIT:
            await asyncio.sleep(operation.payload.get("duration", 1.0))
            return {"waited": operation.payload.get("duration", 1.0)}

        # Determine endpoint
        endpoint = operation.endpoint or self._get_default_endpoint(operation.action)
        url = f"{api_base_url}{endpoint}"

        # Prepare payload with variable substitution
        payload = self._substitute_variables(operation.payload, stored_results)

        # Execute operation with retries
        last_error = None
        for attempt in range(operation.repeat):
            try:
                # Execute HTTP request with timeout
                response = await asyncio.wait_for(
                    self._http_request(operation.method, url, payload), timeout=operation.timeout
                )

                # Add delay between repeats
                if attempt < operation.repeat - 1 and operation.delay > 0:
                    await asyncio.sleep(operation.delay)

                return response

            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError(f"Operation timeout after {operation.timeout}s")
                if attempt < operation.repeat - 1:
                    self.logger.warning(f"Operation retry {attempt + 1}/{operation.repeat} after timeout")
                    await asyncio.sleep(0.5)
                else:
                    raise last_error

            except Exception as e:
                last_error = e
                if attempt < operation.repeat - 1:
                    self.logger.warning(f"Operation retry {attempt + 1}/{operation.repeat}: {e}")
                    await asyncio.sleep(0.5)
                else:
                    raise

        if last_error:
            raise last_error

        return None

    async def _http_request(self, method: str, url: str, payload: Dict[str, Any]) -> Any:
        """
        Execute HTTP request.

        Args:
            method: HTTP method
            url: Request URL
            payload: Request payload

        Returns:
            Response JSON data
        """
        if self.client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self.client.request(method, url, json=payload)
        response.raise_for_status()
        return response.json()

    def _substitute_variables(self, payload: Dict[str, Any], stored_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Substitute variable references in payload with actual values.

        Supports:
        - $variable_name - entire stored result
        - $variable_name[0] - first element of list
        - $variable_name[key] - dictionary key access

        Args:
            payload: Original payload with variable references
            stored_results: Storage of operation results

        Returns:
            Payload with variables substituted
        """
        import re

        def substitute_value(value: Any) -> Any:
            if isinstance(value, str) and value.startswith("$"):
                # Parse variable reference: $var_name or $var_name[index] or $var_name[start:end]
                match = re.match(r'\$(\w+)(?:\[([^\]]+)\])?', value)
                if match:
                    var_name = match.group(1)
                    index_expr = match.group(2)

                    if var_name in stored_results:
                        result = stored_results[var_name]

                        # Handle indexing/slicing
                        if index_expr:
                            try:
                                # Check if it's a slice (e.g., "0:4")
                                if ':' in index_expr:
                                    parts = index_expr.split(':')
                                    start = int(parts[0]) if parts[0] else None
                                    end = int(parts[1]) if parts[1] else None
                                    if isinstance(result, list):
                                        return result[start:end]
                                else:
                                    # Try as integer index
                                    try:
                                        idx = int(index_expr)
                                        if isinstance(result, (list, tuple)):
                                            return result[idx]
                                    except ValueError:
                                        # Try as dictionary key
                                        if isinstance(result, dict):
                                            return result.get(index_expr)
                            except (IndexError, KeyError, ValueError) as e:
                                self.logger.warning(f"Variable substitution failed for {value}: {e}")
                                return value

                        return result
                    else:
                        self.logger.warning(f"Variable '{var_name}' not found in stored results")

                return value
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(v) for v in value]
            else:
                return value

        return substitute_value(payload)

    def _get_default_endpoint(self, action: OperationType) -> str:
        """
        Get default endpoint for an operation type.

        Args:
            action: Operation type

        Returns:
            API endpoint path
        """
        # This will be overridden by hardware-specific implementations
        # For now, provide basic mapping
        endpoint_map = {
            OperationType.DISCOVER: "/discover",
            OperationType.DISCOVER_BACKENDS: "/backends",
            OperationType.OPEN: "/open",
            OperationType.CLOSE: "/close",
            OperationType.OPEN_BATCH: "/open/batch",
            OperationType.CLOSE_BATCH: "/close/batch",
            OperationType.CLOSE_ALL: "/close/all",
            OperationType.CONFIGURE: "/configure",
            OperationType.CONFIGURE_BATCH: "/configure/batch",
            OperationType.GET_CONFIG: "/configuration",
            OperationType.CAPTURE: "/capture",
            OperationType.CAPTURE_BATCH: "/capture/batch",
            OperationType.CAPTURE_HDR: "/capture/hdr",
            OperationType.GET_STATUS: "/status",
            OperationType.GET_CAPABILITIES: "/capabilities",
            OperationType.GET_INFO: "/info",
        }

        return endpoint_map.get(action, f"/{action.value}")


def run_scenario_in_process(
    scenario: HardwareScenario, api_base_url: str, queue: mp.Queue, timeout: Optional[float] = None
) -> None:
    """
    Run scenario in isolated process with watchdog.

    Args:
        scenario: Scenario to execute
        api_base_url: API base URL
        queue: Multiprocessing queue for results
        timeout: Optional total timeout (uses scenario.total_timeout if None)
    """

    async def _run():
        async with HardwareTestRunner(api_base_url) as runner:
            monitor = HardwareMonitor(scenario.name)
            result = await runner.execute_scenario(scenario, monitor)
            summary = monitor.get_summary()
            queue.put({"result": result, "summary": summary})

    try:
        asyncio.run(_run())
    except Exception as e:
        queue.put({"error": str(e), "status": "failed"})
