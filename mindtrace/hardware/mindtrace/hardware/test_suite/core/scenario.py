"""
Base scenario class for hardware testing.

Defines the structure for test scenarios across all hardware types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class OperationType(str, Enum):
    """Types of operations supported in scenarios."""

    # Discovery operations
    DISCOVER = "discover"
    DISCOVER_BACKENDS = "discover_backends"

    # Lifecycle operations
    OPEN = "open"
    CLOSE = "close"
    OPEN_BATCH = "open_batch"
    CLOSE_BATCH = "close_batch"
    CLOSE_ALL = "close_all"

    # Configuration operations
    CONFIGURE = "configure"
    CONFIGURE_BATCH = "configure_batch"
    GET_CONFIG = "get_config"

    # Read/Capture operations
    CAPTURE = "capture"
    CAPTURE_BATCH = "capture_batch"
    CAPTURE_HDR = "capture_hdr"

    # Stream operations
    START_STREAM = "start_stream"
    STOP_STREAM = "stop_stream"
    GET_STREAM_STATUS = "get_stream_status"

    # Status operations
    GET_STATUS = "get_status"
    GET_CAPABILITIES = "get_capabilities"
    GET_INFO = "get_info"

    # Bandwidth operations
    SET_BANDWIDTH_LIMIT = "set_bandwidth_limit"
    GET_BANDWIDTH_SETTINGS = "get_bandwidth_settings"

    # Utility operations
    WAIT = "wait"
    LOOP_START = "loop_start"
    LOOP_END = "loop_end"


@dataclass
class Operation:
    """
    Represents a single operation in a test scenario.

    Attributes:
        action: Type of operation to perform
        endpoint: API endpoint to call (optional, can be auto-determined)
        method: HTTP method (GET, POST, etc.)
        payload: Request payload data
        timeout: Operation timeout in seconds
        repeat: Number of times to repeat this operation
        delay: Delay between repeats in seconds
        expected_success: Whether operation is expected to succeed
        store_result: Variable name to store result for later use
        use_stored: Use stored result from previous operation
    """

    action: OperationType
    endpoint: Optional[str] = None
    method: str = "POST"
    payload: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 5.0
    repeat: int = 1
    delay: float = 0.0
    expected_success: bool = True
    store_result: Optional[str] = None
    use_stored: Optional[str] = None

    def __post_init__(self):
        """Ensure action is OperationType."""
        if isinstance(self.action, str):
            self.action = OperationType(self.action)


@dataclass
class HardwareScenario:
    """
    Base class for hardware test scenarios.

    A scenario defines a sequence of operations to perform against a hardware API,
    along with configuration and expected behavior.

    Attributes:
        name: Scenario name (unique identifier)
        description: Human-readable description
        api_base_url: Base URL for the hardware API
        operations: List of operations to execute
        cleanup_operations: Operations that always run (success or failure)
        timeout_per_operation: Default timeout for operations (seconds)
        total_timeout: Maximum time for entire scenario (seconds)
        expected_success_rate: Minimum expected success rate (0.0-1.0)
        max_retries: Number of retries for failed operations
        retry_delay: Delay between retries (seconds)
        tags: Tags for categorization (e.g., "stress", "chaos", "smoke")
    """

    name: str
    description: str
    api_base_url: str
    operations: List[Operation] = field(default_factory=list)
    cleanup_operations: List[Operation] = field(default_factory=list)
    timeout_per_operation: float = 5.0
    total_timeout: float = 300.0  # 5 minutes default
    expected_success_rate: float = 0.95  # 95% operations should succeed
    max_retries: int = 0  # No retries by default
    retry_delay: float = 0.5
    tags: List[str] = field(default_factory=list)

    def add_operation(self, operation: Operation) -> None:
        """Add an operation to the scenario."""
        self.operations.append(operation)

    def get_operations(self) -> List[Operation]:
        """Get the list of operations."""
        return self.operations

    def estimate_duration(self) -> float:
        """
        Estimate total scenario duration based on operations.

        Returns:
            Estimated duration in seconds
        """
        total = 0.0
        for op in self.operations:
            total += op.timeout * op.repeat
            total += op.delay * (op.repeat - 1) if op.repeat > 1 else 0
        return total

    def validate(self) -> bool:
        """
        Validate scenario configuration.

        Returns:
            True if scenario is valid, raises ValueError otherwise
        """
        if not self.name:
            raise ValueError("Scenario name is required")

        if not self.api_base_url:
            raise ValueError("API base URL is required")

        if not self.operations:
            raise ValueError("Scenario must have at least one operation")

        if self.expected_success_rate < 0.0 or self.expected_success_rate > 1.0:
            raise ValueError("Expected success rate must be between 0.0 and 1.0")

        estimated = self.estimate_duration()
        if estimated > self.total_timeout:
            raise ValueError(
                f"Estimated duration ({estimated}s) exceeds total timeout ({self.total_timeout}s)"
            )

        return True

    def __str__(self) -> str:
        """String representation of scenario."""
        return (
            f"Scenario(name='{self.name}', operations={len(self.operations)}, "
            f"estimated_duration={self.estimate_duration():.1f}s, tags={self.tags})"
        )
