"""Canonical camera configuration contract for configure/get_configuration paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# Keys accepted by AsyncCamera.configure() / returned by get_configuration().
CONFIGURABLE_KEYS: tuple[str, ...] = (
    "exposure_time",
    "gain",
    "roi",
    "trigger_mode",
    "pixel_format",
    "white_balance",
    "image_enhancement",
    "optical_power",
    "packet_size",
    "inter_packet_delay",
    "bandwidth_limit",
    "focus_config",
    "genicam_nodes",
    # OpenCV-specific runtime properties
    "brightness",
    "contrast",
    "saturation",
    "hue",
    "auto_exposure",
    "white_balance_blue_u",
    "white_balance_red_v",
)

# Subset mapped to the service-layer CameraConfiguration response model.
CAMERA_CONFIGURATION_FIELDS: tuple[str, ...] = (
    "exposure_time",
    "gain",
    "roi",
    "trigger_mode",
    "pixel_format",
    "white_balance",
    "image_enhancement",
    "optical_power",
    "packet_size",
    "inter_packet_delay",
    "bandwidth_limit",
)


@dataclass
class ConfigurationApplyResult:
    """Result of applying one or more configuration settings."""

    applied: int
    total: int
    failures: Dict[str, str] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        """True when every recognized key applied and input was not exclusively unrecognized keys."""
        if self.skipped and self.total == 0:
            return False
        return self.applied == self.total


def find_skipped_keys(data: Dict[str, Any]) -> tuple[str, ...]:
    """Return input keys that were not consumed by :func:`normalize_settings`.

    Args:
        data: Raw configure payload or legacy JSON dict.

    Returns:
        Tuple of key names present in the input but not mapped to a configurable setting.
    """
    if not isinstance(data, dict):
        return ()

    skipped: list[str] = []
    if "settings" in data and isinstance(data.get("settings"), dict):
        skipped.extend(key for key in data if key != "settings")

    source = data.get("settings", data)
    if not isinstance(source, dict):
        return tuple(skipped)

    consumed: set[str] = set()

    if "exposure_time" in source:
        consumed.add("exposure_time")
    elif "exposure" in source:
        consumed.add("exposure")

    if "trigger_mode" in source:
        consumed.add("trigger_mode")
    elif "triggermode" in source:
        consumed.add("triggermode")

    if "image_enhancement" in source:
        consumed.add("image_enhancement")
    elif "img_quality_enhancement" in source:
        consumed.add("img_quality_enhancement")

    if "roi" in source:
        consumed.add("roi")
    elif all(key in source for key in ("roi_x", "roi_y", "width", "height")):
        consumed.update(("roi_x", "roi_y", "width", "height"))

    passthrough_keys = set(CONFIGURABLE_KEYS) - {"exposure_time", "trigger_mode", "image_enhancement", "roi"}
    consumed.update(key for key in passthrough_keys if key in source)

    skipped.extend(key for key in source if key not in consumed)
    return tuple(skipped)

def _normalize_roi(value: Any) -> Optional[Tuple[int, int, int, int]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return (
            int(value.get("x", 0)),
            int(value.get("y", 0)),
            int(value.get("width", 0)),
            int(value.get("height", 0)),
        )
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(int(v) for v in value)  # type: ignore[return-value]
    return None


def normalize_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize persisted or legacy export JSON into a configure() payload.

    Args:
        data: Raw JSON dict from disk or legacy backend export.

    Returns:
        Dict containing only recognized configuration keys in canonical form.
    """
    if not isinstance(data, dict):
        return {}

    # Support legacy nested OpenCV format
    source = data.get("settings", data)
    if not isinstance(source, dict):
        source = data

    normalized: Dict[str, Any] = {}

    # Aliases
    if "exposure_time" in source:
        normalized["exposure_time"] = source["exposure_time"]
    elif "exposure" in source:
        normalized["exposure_time"] = source["exposure"]

    if "trigger_mode" in source:
        normalized["trigger_mode"] = source["trigger_mode"]
    elif "triggermode" in source:
        normalized["trigger_mode"] = source["triggermode"]

    if "image_enhancement" in source:
        normalized["image_enhancement"] = source["image_enhancement"]
    elif "img_quality_enhancement" in source:
        normalized["image_enhancement"] = source["img_quality_enhancement"]

    if "roi" in source:
        roi = _normalize_roi(source["roi"])
        if roi is not None:
            normalized["roi"] = roi
    elif all(k in source for k in ("roi_x", "roi_y", "width", "height")):
        normalized["roi"] = (
            int(source["roi_x"]),
            int(source["roi_y"]),
            int(source["width"]),
            int(source["height"]),
        )

    passthrough_keys = set(CONFIGURABLE_KEYS) - {"exposure_time", "trigger_mode", "image_enhancement", "roi"}
    for key in passthrough_keys:
        if key in source:
            normalized[key] = source[key]

    return normalized


def settings_to_camera_configuration_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map normalized settings to CameraConfiguration field values."""
    normalized = normalize_settings(data)
    result: Dict[str, Any] = {}
    for key in CAMERA_CONFIGURATION_FIELDS:
        if key in normalized:
            result[key] = normalized[key]
    return result
