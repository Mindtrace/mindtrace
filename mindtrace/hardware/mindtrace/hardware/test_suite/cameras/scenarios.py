"""
Camera test scenarios.

Predefined test scenarios for camera stress testing, multi-camera coordination,
streaming performance, and chaos testing.
"""

from mindtrace.hardware.test_suite.core.scenario import HardwareScenario, Operation, OperationType


class SmokeTestScenario(HardwareScenario):
    """
    Quick smoke test: Discover, open, capture, close.

    Validates basic camera functionality with minimal operations.
    """

    def __init__(self, api_base_url: str = "http://localhost:8002", backend: str = "GenICam"):
        """
        Initialize smoke test scenario.

        Args:
            api_base_url: Camera API base URL
            backend: Camera backend to test (GenICam, Basler, OpenCV)
        """
        operations = [
            Operation(
                action=OperationType.DISCOVER,
                payload={"backend": backend},
                timeout=10.0,
                store_result="cameras",
            ),
            Operation(
                action=OperationType.OPEN,
                payload={"camera": "$cameras[0]", "test_connection": True},
                timeout=15.0,
                store_result="camera",
            ),
            Operation(
                action=OperationType.CONFIGURE,
                payload={"camera": "$cameras[0]", "properties": {"exposure": 2000}},
                timeout=5.0,
            ),
            Operation(
                action=OperationType.CAPTURE,
                payload={"camera": "$cameras[0]"},
                timeout=10.0,
            ),
        ]

        cleanup_operations = [
            Operation(
                action=OperationType.CLOSE,
                payload={"camera": "$cameras[0]"},
                timeout=5.0,
            ),
        ]

        super().__init__(
            name="smoke_test",
            description=f"Quick smoke test for {backend} camera backend",
            api_base_url=api_base_url,
            operations=operations,
            cleanup_operations=cleanup_operations,
            timeout_per_operation=15.0,
            total_timeout=60.0,
            expected_success_rate=1.0,  # All operations should succeed
            tags=["smoke", "quick", backend.lower()],
        )


class CaptureStressScenario(HardwareScenario):
    """
    Stress test: Rapid continuous capture from single camera.

    Tests camera and API stability under high-frequency capture load.
    """

    def __init__(
        self,
        api_base_url: str = "http://localhost:8002",
        backend: str = "GenICam",
        capture_count: int = 100,
        exposure_us: int = 2000,
    ):
        """
        Initialize capture stress scenario.

        Args:
            api_base_url: Camera API base URL
            backend: Camera backend to test
            capture_count: Number of captures to perform
            exposure_us: Exposure time in microseconds
        """
        operations = [
            Operation(
                action=OperationType.DISCOVER,
                payload={"backend": backend},
                timeout=10.0,
                store_result="cameras",
            ),
            Operation(
                action=OperationType.OPEN,
                payload={"camera": "$cameras[0]", "test_connection": True},
                timeout=15.0,
            ),
            Operation(
                action=OperationType.CONFIGURE,
                payload={"camera": "$cameras[0]", "properties": {"exposure": exposure_us}},
                timeout=5.0,
            ),
            Operation(
                action=OperationType.CAPTURE,
                payload={"camera": "$cameras[0]"},
                timeout=5.0,
                repeat=capture_count,
                delay=0.01,  # 10ms between captures
            ),
        ]

        cleanup_operations = [
            Operation(
                action=OperationType.CLOSE,
                payload={"camera": "$cameras[0]"},
                timeout=5.0,
            ),
        ]

        super().__init__(
            name="capture_stress",
            description=f"Stress test: {capture_count} rapid captures from single {backend} camera",
            api_base_url=api_base_url,
            operations=operations,
            cleanup_operations=cleanup_operations,
            timeout_per_operation=5.0,
            total_timeout=300.0,  # 5 minutes
            expected_success_rate=0.95,  # 95% captures should succeed
            tags=["stress", "capture", backend.lower()],
        )


class MultiCameraScenario(HardwareScenario):
    """
    Multi-camera test: Open multiple cameras, batch capture.

    Tests concurrent camera operations and bandwidth management.
    """

    def __init__(
        self,
        api_base_url: str = "http://localhost:8002",
        backend: str = "GenICam",
        camera_count: int = 4,
        batch_capture_count: int = 50,
        max_concurrent: int = 2,
    ):
        """
        Initialize multi-camera scenario.

        Args:
            api_base_url: Camera API base URL
            backend: Camera backend to test
            camera_count: Number of cameras to open
            batch_capture_count: Number of batch captures to perform
            max_concurrent: Maximum concurrent captures (bandwidth limit)
        """
        operations = [
            Operation(
                action=OperationType.DISCOVER,
                payload={"backend": backend},
                timeout=10.0,
                store_result="cameras",
            ),
            # Note: SET_BANDWIDTH_LIMIT removed - not yet implemented in API
            # Bandwidth management is handled internally by AsyncCameraManager
            Operation(
                action=OperationType.OPEN_BATCH,
                payload={"cameras": f"$cameras[0:{camera_count}]", "test_connection": True},
                timeout=30.0,
            ),
            Operation(
                action=OperationType.CONFIGURE_BATCH,
                payload={
                    "configurations": {
                        f"$cameras[{i}]": {"exposure": 2000} for i in range(camera_count)
                    }
                },
                timeout=10.0,
            ),
            Operation(
                action=OperationType.CAPTURE_BATCH,
                payload={"cameras": f"$cameras[0:{camera_count}]"},
                timeout=15.0,
                repeat=batch_capture_count,
                delay=0.1,  # 100ms between batch captures
            ),
        ]

        cleanup_operations = [
            Operation(
                action=OperationType.CLOSE_BATCH,
                payload={"cameras": f"$cameras[0:{camera_count}]"},
                timeout=10.0,
            ),
        ]

        super().__init__(
            name="multi_camera",
            description=f"Multi-camera test: {camera_count} {backend} cameras, {batch_capture_count} batch captures",
            api_base_url=api_base_url,
            operations=operations,
            cleanup_operations=cleanup_operations,
            timeout_per_operation=15.0,
            total_timeout=600.0,  # 10 minutes
            expected_success_rate=0.90,  # 90% operations should succeed
            tags=["multi-camera", "batch", "bandwidth", backend.lower()],
        )


class StreamStressScenario(HardwareScenario):
    """
    Streaming stress test: Start/stop streaming repeatedly.

    Tests streaming stability and resource cleanup.
    """

    def __init__(
        self,
        api_base_url: str = "http://localhost:8002",
        backend: str = "GenICam",
        stream_cycles: int = 10,
        stream_duration: float = 5.0,
    ):
        """
        Initialize streaming stress scenario.

        Args:
            api_base_url: Camera API base URL
            backend: Camera backend to test
            stream_cycles: Number of stream start/stop cycles
            stream_duration: Duration to keep stream active (seconds)
        """
        operations = [
            Operation(
                action=OperationType.DISCOVER,
                payload={"backend": backend},
                timeout=10.0,
                store_result="cameras",
            ),
            Operation(
                action=OperationType.OPEN,
                payload={"camera": "$cameras[0]", "test_connection": True},
                timeout=15.0,
            ),
            Operation(
                action=OperationType.CONFIGURE,
                payload={"camera": "$cameras[0]", "properties": {"exposure": 10000}},  # 10ms for streaming
                timeout=5.0,
            ),
        ]

        # Add stream start/wait/stop cycles
        for i in range(stream_cycles):
            operations.extend(
                [
                    Operation(
                        action=OperationType.START_STREAM,
                        payload={"camera": "$cameras[0]", "quality": 85, "fps": 30},
                        timeout=10.0,
                    ),
                    Operation(
                        action=OperationType.WAIT,
                        payload={"duration": stream_duration},
                        timeout=stream_duration + 1.0,
                    ),
                    Operation(
                        action=OperationType.STOP_STREAM,
                        payload={"camera": "$cameras[0]"},
                        timeout=5.0,
                    ),
                ]
            )

        cleanup_operations = [
            Operation(
                action=OperationType.CLOSE,
                payload={"camera": "$cameras[0]"},
                timeout=5.0,
            ),
        ]

        super().__init__(
            name="stream_stress",
            description=f"Streaming stress test: {stream_cycles} stream cycles ({stream_duration}s each)",
            api_base_url=api_base_url,
            operations=operations,
            cleanup_operations=cleanup_operations,
            timeout_per_operation=15.0,
            total_timeout=stream_cycles * (stream_duration + 20) + 60,
            expected_success_rate=0.90,
            tags=["stream", "stress", backend.lower()],
        )


class ChaosScenario(HardwareScenario):
    """
    Chaos test: Random operations to find edge cases.

    Deliberately stresses the system with rapid configuration changes,
    concurrent operations, and boundary conditions.
    """

    def __init__(
        self,
        api_base_url: str = "http://localhost:8002",
        backend: str = "GenICam",
        camera_count: int = 2,
    ):
        """
        Initialize chaos scenario.

        Args:
            api_base_url: Camera API base URL
            backend: Camera backend to test
            camera_count: Number of cameras to use
        """
        operations = [
            Operation(
                action=OperationType.DISCOVER,
                payload={"backend": backend},
                timeout=10.0,
                store_result="cameras",
            ),
            # Open multiple cameras
            Operation(
                action=OperationType.OPEN_BATCH,
                payload={"cameras": f"$cameras[0:{camera_count}]", "test_connection": False},
                timeout=30.0,
            ),
            # Rapid configuration changes
            Operation(
                action=OperationType.CONFIGURE,
                payload={"camera": "$cameras[0]", "properties": {"exposure": 1000}},
                timeout=3.0,
            ),
            Operation(
                action=OperationType.CONFIGURE,
                payload={"camera": "$cameras[0]", "properties": {"exposure": 100000}},
                timeout=3.0,
            ),
            Operation(
                action=OperationType.CONFIGURE,
                payload={"camera": "$cameras[0]", "properties": {"exposure": 2000}},
                timeout=3.0,
            ),
            # Capture during configuration
            Operation(
                action=OperationType.CAPTURE,
                payload={"camera": "$cameras[0]"},
                timeout=5.0,
                expected_success=False,  # May fail - that's OK
            ),
            # Close and reopen same camera rapidly
            Operation(
                action=OperationType.CLOSE,
                payload={"camera": "$cameras[0]"},
                timeout=5.0,
            ),
            Operation(
                action=OperationType.OPEN,
                payload={"camera": "$cameras[0]", "test_connection": False},
                timeout=15.0,
            ),
            # Batch operations on mixed states
            Operation(
                action=OperationType.CAPTURE_BATCH,
                payload={"cameras": f"$cameras[0:{camera_count}]"},
                timeout=10.0,
                expected_success=False,  # Some cameras may not be ready
            ),
        ]

        cleanup_operations = [
            Operation(
                action=OperationType.CLOSE_ALL,
                timeout=10.0,
            ),
        ]

        super().__init__(
            name="chaos_test",
            description=f"Chaos test: Random operations on {camera_count} {backend} cameras",
            api_base_url=api_base_url,
            operations=operations,
            cleanup_operations=cleanup_operations,
            timeout_per_operation=15.0,
            total_timeout=300.0,
            expected_success_rate=0.70,  # Lower success rate expected for chaos testing
            tags=["chaos", "edge-cases", backend.lower()],
        )
