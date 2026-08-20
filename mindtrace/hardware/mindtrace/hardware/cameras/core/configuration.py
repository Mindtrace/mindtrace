"""Canonical camera configuration contract for configure/get_configuration paths."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Tuple

from mindtrace.hardware.core.exceptions import CameraConfigurationError

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

# Legacy export_config metadata; may appear beside real settings in saved profiles.
CONFIGURE_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "camera_type",
        "camera_name",
        "timestamp",
        "vendor",
        "model",
        "serial_number",
        # Top-level duplicates when a legacy export also includes a canonical ``roi`` dict.
        "width",
        "height",
        # GenICam legacy export_config metadata.
        "exported_timestamp",
        "exposure_range",
        "gain_range",
        "white_balance_range",
        # OpenCV legacy export_config metadata.
        "camera_index",
    }
)


def skipped_metadata_keys(skipped: tuple[str, ...]) -> tuple[str, ...]:
    """Return skipped input keys that are known legacy export metadata."""
    return tuple(key for key in skipped if key in CONFIGURE_METADATA_KEYS)


def skipped_unexpected_keys(skipped: tuple[str, ...]) -> tuple[str, ...]:
    """Return skipped input keys that are not recognized settings or known metadata."""
    return tuple(key for key in skipped if key not in CONFIGURE_METADATA_KEYS)


@dataclass
class ConfigurationApplyResult:
    """Result of applying one or more configuration settings."""

    applied: int
    total: int
    failures: Dict[str, str] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()
    partial: Dict[str, Any] = field(default_factory=dict)

    @property
    def skipped_metadata(self) -> tuple[str, ...]:
        """Skipped keys that are known legacy export metadata."""
        return skipped_metadata_keys(self.skipped)

    @property
    def skipped_unexpected(self) -> tuple[str, ...]:
        """Skipped keys that are neither configurable settings nor known metadata."""
        return skipped_unexpected_keys(self.skipped)

    @property
    def success(self) -> bool:
        """True when every recognized key applied and no unexpected keys were skipped."""
        if self.failures:
            return False
        if self.skipped_unexpected:
            return False
        return self.applied == self.total


def configuration_error_result(
    error: str,
    settings: Dict[str, Any] | None = None,
) -> ConfigurationApplyResult:
    """Build a failed apply result when configure cannot run per-key apply."""
    return ConfigurationApplyResult(
        applied=0,
        total=len(settings or {}),
        failures={"_error": str(error)},
    )


def configuration_apply_failure_message(
    result: ConfigurationApplyResult,
    *,
    prefix: str,
) -> str:
    """Build a human-readable message for a failed configure apply."""
    parts = [prefix]
    if result.total:
        parts.append(f"{result.applied}/{result.total} settings applied")
    if result.failures:
        parts.append(f"failures: {result.failures}")
    unexpected = result.skipped_unexpected
    if unexpected:
        parts.append(f"skipped unexpected keys: {', '.join(unexpected)}")
    elif result.skipped:
        parts.append(f"skipped keys: {', '.join(result.skipped)}")
    return "; ".join(parts)


def applied_settings_from_result(
    raw_settings: Dict[str, Any],
    result: ConfigurationApplyResult,
) -> Dict[str, Any]:
    """Return normalized settings that were successfully applied in a configure call.

    Nested keys that partially applied (for example ``genicam_nodes``) are taken
    from ``result.partial`` so auto-reinit can replay only the values that landed.

    Args:
        raw_settings: Original configure payload (may include legacy aliases).
        result: Apply result from :meth:`AsyncCamera.configure`.

    Returns:
        Canonical key/value pairs to merge into runtime configure replay state.
    """
    normalized = normalize_settings(raw_settings)
    failed = set(result.failures)
    applied: Dict[str, Any] = {}
    if normalized and result.applied > 0:
        applied = {key: value for key, value in normalized.items() if key not in failed}
    for key, value in result.partial.items():
        if value:
            applied[key] = value
    return applied


def merge_configure_settings(
    existing: Dict[str, Any],
    incoming: Dict[str, Any],
    nested_merge_keys: Iterable[str] = (),
) -> None:
    """Merge applied configure settings into accumulated runtime replay state.

    Scalar keys are overwritten. Keys listed in ``nested_merge_keys`` whose
    values are dicts are updated key-by-key so later configure calls accumulate
    independent nested entries instead of replacing the whole map.

    Args:
        existing: Runtime configure dict for one camera; mutated in place.
        incoming: Newly applied canonical settings from a configure call.
        nested_merge_keys: Configure keys declared by the backend as nested
            maps that should accumulate (see
            :attr:`~mindtrace.hardware.cameras.backends.camera_backend.CameraBackend.nested_merge_config_keys`).
    """
    nested = frozenset(nested_merge_keys)
    for key, value in incoming.items():
        current = existing.get(key)
        if key in nested and isinstance(current, dict) and isinstance(value, dict):
            current.update(value)
        elif isinstance(value, dict):
            existing[key] = dict(value)
        else:
            existing[key] = value


def applied_subset_from_exception(exc: BaseException) -> Dict[str, Any]:
    """Return nested values that applied before ``exc`` was raised, if recorded.

    :class:`~mindtrace.hardware.core.exceptions.CameraConfigurationError` stores
    that subset under ``details["applied"]``.
    """
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return {}
    applied = details.get("applied")
    return applied if isinstance(applied, dict) else {}


def configuration_apply_result_to_dict(result: ConfigurationApplyResult) -> Dict[str, Any]:
    """Serialize a configure apply result for service and client responses."""
    return {
        "applied": result.applied,
        "total": result.total,
        "failures": dict(result.failures),
        "skipped": list(result.skipped),
        "skipped_metadata": list(result.skipped_metadata),
        "skipped_unexpected": list(result.skipped_unexpected),
        "partial": dict(result.partial),
        "success": result.success,
    }


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


_ROI_DICT_KEYS = ("x", "y", "width", "height")
_LEGACY_ROI_KEYS = ("roi_x", "roi_y", "width", "height")
# Legacy Basler export_config wrote explicit null for non-GigE cameras; treat as absent.
_GIGE_PASSTHROUGH_KEYS = frozenset({"packet_size", "inter_packet_delay", "bandwidth_limit"})


def _normalize_roi(value: Any) -> Tuple[int, int, int, int]:
    """Parse a canonical ROI value into ``(x, y, width, height)``.

    Raises:
        ValueError: If ``value`` is not a complete 4-int rectangle.
    """
    if isinstance(value, dict):
        missing = [key for key in _ROI_DICT_KEYS if key not in value]
        if missing:
            raise ValueError(f"roi dict missing keys: {', '.join(missing)}")
        return (
            int(value["x"]),
            int(value["y"]),
            int(value["width"]),
            int(value["height"]),
        )
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(int(v) for v in value)  # type: ignore[return-value]
    raise ValueError("roi must be a 4-int (x, y, width, height) tuple or {x, y, width, height} dict")


def parse_configure_settings(data: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Normalize a configure payload and collect recognized keys with invalid values.

    Args:
        data: Raw configure payload or legacy JSON dict.

    Returns:
        Tuple of ``(normalized, invalid)`` where ``invalid`` maps canonical keys
        to error messages. Invalid values are omitted from ``normalized``.
    """
    if not isinstance(data, dict):
        return {}, {}

    source = data.get("settings", data)
    if not isinstance(source, dict):
        source = data

    normalized: Dict[str, Any] = {}
    invalid: Dict[str, str] = {}

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
        try:
            normalized["roi"] = _normalize_roi(source["roi"])
        except (TypeError, ValueError) as exc:
            invalid["roi"] = str(exc)
    elif all(key in source for key in _LEGACY_ROI_KEYS):
        try:
            normalized["roi"] = (
                int(source["roi_x"]),
                int(source["roi_y"]),
                int(source["width"]),
                int(source["height"]),
            )
        except (TypeError, ValueError) as exc:
            invalid["roi"] = str(exc)

    passthrough_keys = set(CONFIGURABLE_KEYS) - {"exposure_time", "trigger_mode", "image_enhancement", "roi"}
    for key in passthrough_keys:
        if key not in source:
            continue
        value = source[key]
        if value is None and key in _GIGE_PASSTHROUGH_KEYS:
            continue
        if isinstance(value, dict) and not value:
            continue
        normalized[key] = value

    return normalized, invalid


def normalize_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize persisted or legacy export JSON into a configure() payload.

    Args:
        data: Raw JSON dict from disk or legacy backend export.

    Returns:
        Dict containing only recognized configuration keys in canonical form.
        Keys whose values cannot be parsed (for example a malformed ``roi``)
        are omitted.
    """
    normalized, _invalid = parse_configure_settings(data)
    return normalized


def settings_to_camera_configuration_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map normalized settings to CameraConfiguration field values.

    Includes every canonical configure key present in ``data`` so GET
    endpoints return the same payload shape as configure/export.
    """
    normalized = normalize_settings(data)
    return {key: normalized[key] for key in CONFIGURABLE_KEYS if key in normalized}


def load_config_json(path: Path | str) -> Dict[str, Any]:
    """Load configuration JSON from disk.

    Args:
        path: Path to a saved profile or explicit config file.

    Returns:
        Parsed configuration dict.

    Raises:
        CameraConfigurationError: If the file contains invalid JSON.
    """
    config_path = Path(path)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            return json.load(config_file)
    except json.JSONDecodeError as exc:
        raise CameraConfigurationError(f"Invalid config JSON at {config_path}: {exc}") from exc
