"""
Configuration loader for camera test scenarios.

Loads test configurations from YAML files.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class ConfigLoader:
    """Load and parse test configuration files."""

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize config loader.

        Args:
            config_dir: Directory containing config files (default: cameras/config/)
        """
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
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Available configs: {available}"
            )

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
        required_sections = ["name", "api", "hardware", "test", "expectations"]

        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required section in config: {section}")

        # Validate API section
        if "base_url" not in config["api"]:
            raise ValueError("Missing 'base_url' in api section")

        # Validate hardware section
        if "backend" not in config["hardware"]:
            raise ValueError("Missing 'backend' in hardware section")

        # Validate expectations
        if "total_timeout" not in config["expectations"]:
            raise ValueError("Missing 'total_timeout' in expectations section")


# Convenience function
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
