"""
Scenario factory for creating test scenarios from YAML configurations.

YAML-based scenario creation - all scenario logic defined in YAML files.
"""

from typing import Any, Dict, List

from mindtrace.hardware.test_suite.cameras.config_loader import load_config
from mindtrace.hardware.test_suite.core.scenario import HardwareScenario, Operation, OperationType


def _parse_operation(op_dict: Dict[str, Any]) -> Operation:
    """
    Parse a single operation from YAML dictionary.

    Args:
        op_dict: Operation dictionary from YAML

    Returns:
        Operation instance
    """
    # Convert action string to OperationType enum
    action = OperationType(op_dict["action"])

    # Extract optional fields with defaults
    return Operation(
        action=action,
        endpoint=op_dict.get("endpoint"),
        method=op_dict.get("method", "POST"),
        payload=op_dict.get("payload", {}),
        timeout=op_dict.get("timeout", 5.0),
        repeat=op_dict.get("repeat", 1),
        delay=op_dict.get("delay", 0.0),
        expected_success=op_dict.get("expected_success", True),
        store_result=op_dict.get("store_result"),
        use_stored=op_dict.get("use_stored"),
    )


def create_scenario_from_config(config_name: str) -> HardwareScenario:
    """
    Create a test scenario from a YAML configuration file.

    This is the generic factory - all scenario logic is defined in YAML.
    No Python classes required for new scenarios.

    Args:
        config_name: Name of config file (e.g., "smoke_test" or "smoke_test.yaml")

    Returns:
        Configured HardwareScenario instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required YAML fields are missing
        KeyError: If YAML structure is invalid
    """
    # Load configuration
    config = load_config(config_name)

    # Validate required top-level keys
    required_keys = ["name", "description", "api", "expectations"]
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ValueError(f"Missing required YAML keys: {missing_keys}")

    # Validate operations exist
    if "operations" not in config or not config["operations"]:
        raise ValueError(f"Scenario '{config['name']}' must have at least one operation")

    # Parse operations from YAML
    operations = [_parse_operation(op) for op in config["operations"]]

    # Parse cleanup operations (optional)
    cleanup_operations = []
    if "cleanup_operations" in config and config["cleanup_operations"]:
        cleanup_operations = [_parse_operation(op) for op in config["cleanup_operations"]]

    # Extract configuration values with defaults
    api_base_url = config["api"]["base_url"]
    timeout_per_operation = config["expectations"].get("timeout_per_operation", 5.0)
    total_timeout = config["expectations"].get("total_timeout", 300.0)
    expected_success_rate = config["expectations"].get("expected_success_rate", 0.95)
    tags = config.get("tags", [])

    # Create scenario with parsed operations
    scenario = HardwareScenario(
        name=config["name"],
        description=config["description"],
        api_base_url=api_base_url,
        operations=operations,
        cleanup_operations=cleanup_operations,
        timeout_per_operation=timeout_per_operation,
        total_timeout=total_timeout,
        expected_success_rate=expected_success_rate,
        tags=tags,
    )

    # Validate scenario
    scenario.validate()

    return scenario
