"""
Parameter validator for camera test configurations.

Validates test config parameters against CameraSettings to ensure
API alignment and prevent configuration errors.
"""

from dataclasses import fields
from typing import Any, Dict, List, Optional, Set, Tuple

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.config import CameraSettings


class ParameterCategory:
    """Parameter categories from CameraSettings."""

    # RUNTIME-CONFIGURABLE PARAMETERS (changeable via configure_camera API)
    RUNTIME = {
        "timeout_ms",
        "exposure_time",
        "gain",
        "trigger_mode",
        "white_balance",
        "image_quality_enhancement",
        "pixel_format",
        "opencv_default_width",
        "opencv_default_height",
        "opencv_default_fps",
        "opencv_default_exposure",
    }

    # STARTUP-ONLY PARAMETERS (require camera reinitialization)
    STARTUP = {
        "buffer_count",
        "basler_multicast_enabled",
        "basler_multicast_group",
        "basler_multicast_port",
        "basler_target_ips",
    }

    # SYSTEM CONFIGURATION (manager-level settings)
    SYSTEM = {
        "retrieve_retry_count",
        "max_concurrent_captures",
        "max_camera_index",
        "mock_camera_count",
        "enhancement_gamma",
        "enhancement_contrast",
        "opencv_exposure_range_min",
        "opencv_exposure_range_max",
        "opencv_width_range_min",
        "opencv_width_range_max",
        "opencv_height_range_min",
        "opencv_height_range_max",
    }


class ParameterValidator(Mindtrace):
    """Validates camera configuration parameters against CameraSettings."""

    def __init__(self, **kwargs):
        """Initialize validator with CameraSettings fields.

        Args:
            **kwargs: Additional Mindtrace initialization parameters
        """
        super().__init__(**kwargs)

        self._all_parameters: Set[str] = set()
        self._parameter_types: Dict[str, type] = {}

        # Extract all fields from CameraSettings
        for field in fields(CameraSettings):
            self._all_parameters.add(field.name)
            self._parameter_types[field.name] = field.type

        self.logger.debug(f"ParameterValidator initialized with {len(self._all_parameters)} parameters")

    def validate_parameters(
        self,
        parameters: Dict[str, Any],
        category: Optional[str] = None,
        strict: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Validate parameters against CameraSettings.

        Args:
            parameters: Dictionary of parameter names and values to validate
            category: Expected category ("runtime", "startup", "system", or None for any)
            strict: If True, raise errors; if False, return warnings

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        for param_name, param_value in parameters.items():
            # Check if parameter exists
            if param_name not in self._all_parameters:
                # Try to find similar parameter
                suggestion = self._find_similar_parameter(param_name)
                if suggestion:
                    errors.append(
                        f"Unknown parameter '{param_name}'. "
                        f"Did you mean '{suggestion}'? (matches CameraSettings.{suggestion})"
                    )
                else:
                    errors.append(
                        f"Unknown parameter '{param_name}'. "
                        f"Not found in CameraSettings."
                    )
                continue

            # Check category if specified
            if category:
                expected_category = self._get_parameter_category(param_name)
                if expected_category != category:
                    errors.append(
                        f"Parameter '{param_name}' is in category '{expected_category}', "
                        f"but was specified in '{category}' section. "
                        f"Move to camera_config.{expected_category}"
                    )

            # Check type (basic validation)
            expected_type = self._parameter_types.get(param_name)
            if expected_type and not self._check_type_compatibility(param_value, expected_type):
                errors.append(
                    f"Parameter '{param_name}' has wrong type. "
                    f"Expected {expected_type}, got {type(param_value)}"
                )

        is_valid = len(errors) == 0
        return (is_valid, errors)

    def validate_config(
        self,
        config: Dict[str, Any],
        strict: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validate entire test configuration.

        Args:
            config: Test configuration dictionary
            strict: If True, errors are fatal; if False, show warnings

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        all_errors = []

        # Validate camera_config section if present
        if "camera_config" in config:
            camera_config = config["camera_config"]

            # Validate runtime parameters
            if "runtime" in camera_config:
                is_valid, errors = self.validate_parameters(
                    camera_config["runtime"],
                    category="runtime",
                    strict=strict
                )
                all_errors.extend(errors)

            # Validate startup parameters
            if "startup" in camera_config:
                is_valid, errors = self.validate_parameters(
                    camera_config["startup"],
                    category="startup",
                    strict=strict
                )
                all_errors.extend(errors)

            # Validate system parameters
            if "system" in camera_config:
                is_valid, errors = self.validate_parameters(
                    camera_config["system"],
                    category="system",
                    strict=strict
                )
                all_errors.extend(errors)

        # Check for old-style parameters in operations
        if "operations" in config:
            for i, operation in enumerate(config["operations"]):
                if operation.get("action") in ["configure", "configure_batch"]:
                    if "payload" in operation and "properties" in operation["payload"]:
                        properties = operation["payload"]["properties"]

                        # Skip if properties is a variable reference
                        if isinstance(properties, str) and properties.startswith("$"):
                            continue

                        if isinstance(properties, dict):
                            is_valid, errors = self.validate_parameters(
                                properties,
                                category=None,  # Allow any category in operation
                                strict=strict
                            )
                            # Prefix errors with operation index
                            prefixed_errors = [
                                f"Operation {i} (configure): {error}"
                                for error in errors
                            ]
                            all_errors.extend(prefixed_errors)

        is_valid = len(all_errors) == 0
        return (is_valid, all_errors)

    def _get_parameter_category(self, param_name: str) -> str:
        """Determine which category a parameter belongs to."""
        if param_name in ParameterCategory.RUNTIME:
            return "runtime"
        elif param_name in ParameterCategory.STARTUP:
            return "startup"
        elif param_name in ParameterCategory.SYSTEM:
            return "system"
        else:
            return "unknown"

    def _find_similar_parameter(self, param_name: str) -> Optional[str]:
        """Find similar parameter name using fuzzy matching."""
        param_name_lower = param_name.lower()

        # Try exact match (case-insensitive)
        for known_param in self._all_parameters:
            if known_param.lower() == param_name_lower:
                return known_param

        # Try common mistakes
        common_mistakes = {
            "exposure": "exposure_time",
            "timeout": "timeout_ms",
            "retry": "retrieve_retry_count",
            "retries": "retrieve_retry_count",
            "concurrent": "max_concurrent_captures",
            "buffer": "buffer_count",
            "buffers": "buffer_count",
        }

        if param_name_lower in common_mistakes:
            return common_mistakes[param_name_lower]

        # Try substring matching
        for known_param in self._all_parameters:
            if param_name_lower in known_param.lower() or known_param.lower() in param_name_lower:
                return known_param

        return None

    def _check_type_compatibility(self, value: Any, expected_type: type) -> bool:
        """Check if value is compatible with expected type."""
        # Handle string type annotations
        if expected_type is str:
            return isinstance(value, str)
        elif expected_type is int:
            return isinstance(value, int)
        elif expected_type is float:
            return isinstance(value, (int, float))
        elif expected_type is bool:
            return isinstance(value, bool)
        else:
            # For complex types, just accept it
            return True

    def get_all_parameters(self, category: Optional[str] = None) -> Set[str]:
        """
        Get all valid parameter names.

        Args:
            category: Filter by category ("runtime", "startup", "system", or None for all)

        Returns:
            Set of parameter names
        """
        if category == "runtime":
            return ParameterCategory.RUNTIME
        elif category == "startup":
            return ParameterCategory.STARTUP
        elif category == "system":
            return ParameterCategory.SYSTEM
        else:
            return self._all_parameters

    def print_parameter_reference(self) -> str:
        """Generate parameter reference documentation."""
        lines = []
        lines.append("# Camera Configuration Parameters")
        lines.append("")
        lines.append("## Runtime-Configurable Parameters")
        lines.append("(Can be changed during operation via /cameras/configure)")
        lines.append("")
        for param in sorted(ParameterCategory.RUNTIME):
            lines.append(f"- {param}")

        lines.append("")
        lines.append("## Startup-Only Parameters")
        lines.append("(Require camera reinitialization)")
        lines.append("")
        for param in sorted(ParameterCategory.STARTUP):
            lines.append(f"- {param}")

        lines.append("")
        lines.append("## System Configuration Parameters")
        lines.append("(Manager-level settings)")
        lines.append("")
        for param in sorted(ParameterCategory.SYSTEM):
            lines.append(f"- {param}")

        return "\n".join(lines)


# Convenience functions
_validator = None


def get_validator() -> ParameterValidator:
    """Get singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = ParameterValidator()
    return _validator


def validate_parameters(
    parameters: Dict[str, Any],
    category: Optional[str] = None,
    strict: bool = True
) -> Tuple[bool, List[str]]:
    """Validate parameters against CameraSettings."""
    validator = get_validator()
    return validator.validate_parameters(parameters, category, strict)


def validate_config(
    config: Dict[str, Any],
    strict: bool = False
) -> Tuple[bool, List[str]]:
    """Validate entire test configuration."""
    validator = get_validator()
    return validator.validate_config(config, strict)
