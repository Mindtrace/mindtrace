"""
Scenario factory for creating test scenarios from YAML configurations.
"""

from typing import Dict, Any

from mindtrace.hardware.test_suite.cameras.config_loader import load_config
from mindtrace.hardware.test_suite.cameras.scenarios import (
    SmokeTestScenario,
    CaptureStressScenario,
    MultiCameraScenario,
    StreamStressScenario,
    ChaosScenario,
)
from mindtrace.hardware.test_suite.core.scenario import HardwareScenario


def create_scenario_from_config(config_name: str) -> HardwareScenario:
    """
    Create a test scenario from a YAML configuration file.

    Args:
        config_name: Name of config file (e.g., "smoke_test" or "smoke_test.yaml")

    Returns:
        Configured HardwareScenario instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If scenario type is unknown
    """
    # Load configuration
    config = load_config(config_name)

    # Extract common parameters
    api_base_url = config["api"]["base_url"]
    backend = config["hardware"]["backend"]
    scenario_name = config["name"]

    # Create appropriate scenario based on name
    if scenario_name == "smoke_test":
        scenario = SmokeTestScenario(
            api_base_url=api_base_url,
            backend=backend,
        )

    elif scenario_name == "capture_stress":
        scenario = CaptureStressScenario(
            api_base_url=api_base_url,
            backend=backend,
            capture_count=config["test"]["capture_count"],
            exposure_us=config["test"]["exposure_us"],
        )

    elif scenario_name == "multi_camera":
        scenario = MultiCameraScenario(
            api_base_url=api_base_url,
            backend=backend,
            camera_count=config["hardware"]["camera_count"],
            batch_capture_count=config["test"]["batch_capture_count"],
            max_concurrent=config["test"]["max_concurrent_captures"],
        )

    elif scenario_name == "stream_stress":
        scenario = StreamStressScenario(
            api_base_url=api_base_url,
            backend=backend,
            stream_cycles=config["test"]["stream_cycles"],
            stream_duration=config["test"]["stream_duration"],
        )

    elif scenario_name == "chaos_test":
        scenario = ChaosScenario(
            api_base_url=api_base_url,
            backend=backend,
            camera_count=config["hardware"]["camera_count"],
        )

    elif scenario_name == "soak_test":
        # Soak test uses capture stress with higher counts
        scenario = CaptureStressScenario(
            api_base_url=api_base_url,
            backend=backend,
            capture_count=config["test"]["capture_count"],
            exposure_us=config["test"]["exposure_us"],
        )

    else:
        raise ValueError(
            f"Unknown scenario type: {scenario_name}. "
            f"Available: smoke_test, capture_stress, multi_camera, stream_stress, chaos_test, soak_test"
        )

    # Override expectations from config
    if "expectations" in config:
        if "total_timeout" in config["expectations"]:
            scenario.total_timeout = config["expectations"]["total_timeout"]
        if "expected_success_rate" in config["expectations"]:
            scenario.expected_success_rate = config["expectations"]["expected_success_rate"]

    return scenario
