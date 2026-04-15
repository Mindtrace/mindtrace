"""Capture group management for stage+set based semaphore routing.

Ported from mt-rix CameraBackend stage_set_configs pattern. Provides per-group
concurrency control for production-line camera batching.

Usage::

    config = {
        "inspection": {
            "top_cameras": {"batch_size": 3, "cameras": ["Basler:cam1", "Basler:cam2"]},
            "side_cameras": {"batch_size": 1, "cameras": ["Basler:cam3"]},
        }
    }
    is_valid, err = validate_stage_set_configs(config, ["Basler:cam1", "Basler:cam2", "Basler:cam3"])
    groups, camera_map = build_capture_groups(config)
    sem, err = get_semaphore_for_capture("Basler:cam1", "inspection", "top_cameras", groups, camera_map, global_sem)
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Type alias for the nested config format from mt-rix:
# {stage: {set: {"batch_size": int, "cameras": [str]}}}
StageSetConfigDict = Dict[str, Dict[str, Dict[str, Union[int, List[str]]]]]


@dataclass
class CaptureGroup:
    """A stage+set capture group with its own concurrency semaphore.

    Each group limits how many cameras within it can capture simultaneously,
    allowing fine-grained bandwidth management on production lines.
    """

    stage: str
    set_name: str
    max_concurrent: int
    cameras: Set[str] = field(default_factory=set)
    semaphore: asyncio.Semaphore = field(init=False, repr=False)

    def __post_init__(self):
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

    @property
    def key(self) -> str:
        """String key for this group: 'stage:set_name'."""
        return f"{self.stage}:{self.set_name}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-friendly dict (excludes semaphore)."""
        return {
            "stage": self.stage,
            "set_name": self.set_name,
            "max_concurrent": self.max_concurrent,
            "cameras": sorted(self.cameras),
        }


def validate_stage_set_configs(
    config: StageSetConfigDict,
    available_cameras: List[str],
) -> Tuple[bool, Optional[str]]:
    """Validate stage_set_configs nested dictionary structure.

    Rules:
        - Each stage+set entry must have ``batch_size`` (int > 0) and ``cameras`` (list[str]).
        - All cameras must exist in *available_cameras*.
        - A camera cannot appear in multiple sets within the same stage.

    Args:
        config: ``{stage: {set: {"batch_size": int, "cameras": [str]}}}``
        available_cameras: Camera names that are currently initialized.

    Returns:
        ``(is_valid, error_message)`` -- *error_message* is ``None`` when valid.
    """
    if not config:
        return True, None

    # Track camera assignments per stage for duplicate detection
    stage_camera_sets: Dict[str, Dict[str, List[str]]] = {}

    for stage, sets_dict in config.items():
        if not isinstance(sets_dict, dict):
            return False, f"Expected dict of sets for stage='{stage}', got {type(sets_dict).__name__}"

        if stage not in stage_camera_sets:
            stage_camera_sets[stage] = {}

        for set_name, set_config in sets_dict.items():
            if not isinstance(set_config, dict):
                return False, (f"Invalid config structure for stage='{stage}', set='{set_name}'. Expected dict.")

            if "batch_size" not in set_config or "cameras" not in set_config:
                return False, (f"Missing 'batch_size' or 'cameras' in stage='{stage}', set='{set_name}'")

            batch_size = set_config["batch_size"]
            cameras = set_config["cameras"]

            if not isinstance(batch_size, int) or batch_size <= 0:
                return False, (f"batch_size must be a positive integer for stage='{stage}', set='{set_name}'")

            if not isinstance(cameras, list):
                return False, f"'cameras' must be a list for stage='{stage}', set='{set_name}'"

            for camera in cameras:
                if camera not in available_cameras:
                    return False, (f"Camera '{camera}' in stage_set_configs not found in active cameras")

            if set_name not in stage_camera_sets[stage]:
                stage_camera_sets[stage][set_name] = []
            stage_camera_sets[stage][set_name].extend(cameras)

    # Check for cameras in multiple sets within the same stage
    for stage, sets_dict in stage_camera_sets.items():
        all_cameras_in_stage: List[str] = []
        for set_name, cameras in sets_dict.items():
            for camera in cameras:
                if camera in all_cameras_in_stage:
                    return False, (f"Camera '{camera}' cannot be in multiple sets within the same stage ('{stage}')")
                all_cameras_in_stage.append(camera)

    return True, None


def build_capture_groups(
    config: StageSetConfigDict,
) -> Tuple[Dict[str, CaptureGroup], Dict[str, List[str]]]:
    """Build CaptureGroup objects and camera-to-group-key mapping from config.

    Args:
        config: ``{stage: {set: {"batch_size": int, "cameras": [str]}}}``

    Returns:
        ``(groups_by_key, camera_to_group_keys)``

        - ``groups_by_key``: ``{"stage:set": CaptureGroup, ...}``
        - ``camera_to_group_keys``: ``{"cam_name": ["stage:set", ...], ...}``
    """
    groups: Dict[str, CaptureGroup] = {}
    camera_map: Dict[str, List[str]] = {}

    for stage, sets_dict in config.items():
        for set_name, set_config in sets_dict.items():
            batch_size = set_config["batch_size"]
            cameras = set_config["cameras"]

            group = CaptureGroup(
                stage=stage,
                set_name=set_name,
                max_concurrent=batch_size,
                cameras=set(cameras),
            )
            groups[group.key] = group

            for cam in cameras:
                if cam not in camera_map:
                    camera_map[cam] = []
                if group.key not in camera_map[cam]:
                    camera_map[cam].append(group.key)

    return groups, camera_map


def get_semaphore_for_capture(
    camera_name: str,
    stage: Optional[str],
    set_name: Optional[str],
    capture_groups: Dict[str, CaptureGroup],
    camera_group_keys: Dict[str, List[str]],
    global_semaphore: asyncio.Semaphore,
) -> Tuple[Optional[asyncio.Semaphore], Optional[str]]:
    """3-way semaphore routing for capture operations.

    Decision tree (ported from mt-rix ``_get_semaphore_for_capture``):

    1. *stage* + *set_name* provided AND camera is assigned -> group semaphore
    2. Camera HAS group assignments but stage/set not provided -> **error**
    3. No assignments, no stage/set -> global semaphore

    Args:
        camera_name: Camera identifier.
        stage: Optional stage name.
        set_name: Optional set name.
        capture_groups: Current capture groups by key.
        camera_group_keys: Camera-to-group-key mapping.
        global_semaphore: Fallback global semaphore.

    Returns:
        ``(semaphore, error_message)`` -- *error_message* is ``None`` on success,
        *semaphore* is ``None`` on error.
    """
    if stage is not None and set_name is not None:
        group_key = f"{stage}:{set_name}"
        camera_assignments = camera_group_keys.get(camera_name, [])

        if group_key in camera_assignments:
            if group_key in capture_groups:
                return capture_groups[group_key].semaphore, None
            else:
                # Group key registered for camera but semaphore missing — fall back
                return global_semaphore, None
        else:
            return None, (
                f"Camera '{camera_name}' is not assigned to stage='{stage}', "
                f"set='{set_name}'. Available assignments: {camera_assignments}"
            )

    elif camera_name in camera_group_keys and len(camera_group_keys[camera_name]) > 0:
        available = camera_group_keys[camera_name]
        return None, (
            f"Camera '{camera_name}' has capture group assignments {available} but "
            f"stage and set_name were not provided in request"
        )

    else:
        return global_semaphore, None
