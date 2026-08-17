"""Canonical camera configuration contract for configure/get_configuration paths."""

from __future__ import annotations

from collections.abc import Iterable
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


@dataclass
class ConfigurationApplyResult:
    """Result of applying one or more configuration settings."""

    applied: int
    total: int
    failures: Dict[str, str] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()
    partial: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True when every recognized key applied and input was not exclusively unrecognized keys."""
        if self.skipped and self.total == 0:
            return False
        return self.applied == self.total


def configuration_error_result(
    error: str,
    settings: Dict[str, Any] | None = None,
) -> ConfigurationApplyResult:
    """Build a failed apply result when configure cannot run per-key apply.

    ``total`` is the number of keys in ``settings``, or 1 when the payload is
    empty, so ``success`` is False even for ``configure(camera, {})``.
    """
    total = max(len(settings or {}), 1)
    return ConfigurationApplyResult(
        applied=0,
        total=total,
        failures={"_error": str(error)},
    )


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
    """Map normalized settings to CameraConfiguration field values.

    Includes every canonical configure key present in ``data`` so GET
    endpoints return the same payload shape as configure/export.
    """
    normalized = normalize_settings(data)
    return {key: normalized[key] for key in CONFIGURABLE_KEYS if key in normalized}
