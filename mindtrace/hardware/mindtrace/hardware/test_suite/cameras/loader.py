"""
Camera test scenario loader.

Loads YAML configuration files and creates scenario objects.
Combines configuration loading and scenario creation in one module.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from mindtrace.core import Mindtrace
from mindtrace.hardware.test_suite.cameras.validator import validate_config
from mindtrace.hardware.test_suite.core.models import HardwareScenario, Operation, OperationType


class ConfigLoader(Mindtrace):
    """Load and parse test configuration files."""

    def __init__(self, config_dir: Optional[str] = None, **kwargs):
        """
        Initialize config loader.

        Args:
            config_dir: Directory containing config files (default: cameras/config/)
            **kwargs: Additional Mindtrace initialization parameters
        """
        super().__init__(**kwargs)

        if config_dir is None:
            # Default to config directory relative to this file
            self.config_dir = Path(__file__).parent / "config"
        else:
            self.config_dir = Path(config_dir)

        if not self.config_dir.exists():
            raise ValueError(f"Config directory does not exist: {self.config_dir}")

    def list_configs(self) -> List[str]:
        """
        List available configuration files.

        Returns:
            List of config names (without .yaml extension)
        """
        configs = []
        for file in self.config_dir.glob("*.yaml"):
            configs.append(file.stem)
        return sorted(configs)

    def load_config(self, config_name: str) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Args:
            config_name: Name of config file (with or without .yaml extension)

        Returns:
            Dictionary with configuration data

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        # Add .yaml extension if not present
        if not config_name.endswith(".yaml"):
            config_name = f"{config_name}.yaml"

        config_path = self.config_dir / config_name

        if not config_path.exists():
            available = ", ".join(self.list_configs())
            raise FileNotFoundError(f"Config file not found: {config_path}\nAvailable configs: {available}")

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            # Validate required fields
            self._validate_config(config)

            return config

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file {config_path}: {e}")

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration structure.

        Args:
            config: Configuration dictionary

        Raises:
            ValueError: If required fields are missing
        """
        # Core required sections for both old and new format
        required_sections = ["name", "api", "expectations"]

        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required section in config: {section}")

        # Validate API section
        if "base_url" not in config["api"]:
            raise ValueError("Missing 'base_url' in api section")

        # Validate expectations
        if "total_timeout" not in config["expectations"]:
            raise ValueError("Missing 'total_timeout' in expectations section")

        # New format: must have operations
        # Old format: must have hardware and test sections
        has_operations = "operations" in config and config["operations"]
        has_old_format = "hardware" in config and "test" in config

        if not has_operations and not has_old_format:
            raise ValueError(
                "Config must have either 'operations' section (new format) "
                "or both 'hardware' and 'test' sections (old format)"
            )

        # Validate hardware section if present
        if "hardware" in config and "backend" not in config["hardware"]:
            raise ValueError("Missing 'backend' in hardware section")

        # Validate camera configuration parameters against CameraSettings
        is_valid, errors = validate_config(config, strict=False)

        if errors:
            # Log warnings for parameter issues
            self.logger.warning("Configuration validation warnings for config:")
            for error in errors:
                self.logger.warning(f"  - {error}")

            # For now, we only warn - don't fail the config load
            # This allows gradual migration from old to new format
            # TODO: Enable strict validation after all configs are migrated


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


# Convenience functions
def load_config(config_name: str) -> Dict[str, Any]:
    """
    Load a test configuration.

    Args:
        config_name: Name of config file (e.g., "smoke_test" or "smoke_test.yaml")

    Returns:
        Configuration dictionary
    """
    loader = ConfigLoader()
    return loader.load_config(config_name)


def list_available_configs() -> List[str]:
    """
    List all available test configurations.

    Returns:
        List of config names
    """
    loader = ConfigLoader()
    return loader.list_configs()
