"""Side-effect-free normalization and validation shared by batch save entry points."""

from collections import defaultdict
from copy import deepcopy
from typing import Any

from mindtrace.registry.core.types import Version


def normalize_save_batch(
    names: list[str],
    objs: Any | list[Any],
    versions: str | None | list[str | None],
    init_params: dict[str, Any] | list[dict[str, Any]] | None,
    metadata: dict[str, Any] | list[dict[str, Any]] | None,
) -> tuple[list[Any], list[str | None], list[dict[str, Any] | None], list[dict[str, Any] | None]]:
    """Broadcast scalar inputs, check lengths, and isolate each item's dictionaries."""
    values = [
        value if isinstance(value, list) else [value] * len(names) for value in (objs, versions, init_params, metadata)
    ]
    if any(len(value) != len(names) for value in values):
        raise ValueError("All list inputs must have the same length")
    objects, versions_list, params_list, metadata_list = values
    return objects, versions_list, [deepcopy(p) for p in params_list], [deepcopy(m) for m in metadata_list]


def validate_save_batch(
    names: list[str], versions: list[str | None], *, version_objects: bool, version_digits: int
) -> None:
    """Reject ambiguous repeated names and duplicate identities before any saves.

    Only repeated names need identity preflight. Unique-name version validation
    and automatic selection retain their existing per-item error semantics.
    """
    positions: dict[str, list[int]] = defaultdict(list)
    for index, name in enumerate(names):
        positions[name].append(index)
    for name, indices in positions.items():
        if len(indices) < 2:
            continue
        if not version_objects:
            raise ValueError(
                f"Duplicate batch identity for '{name}': repeated names are not allowed in unversioned mode"
            )
        seen: dict[str, int] = {}
        for index in indices:
            version = versions[index]
            if version is None or version == "latest":
                raise ValueError(f"Repeated batch name '{name}' requires an explicit numeric version for every input")
            try:
                normalized = str(Version(version, digits=version_digits))
            except ValueError as exc:
                raise ValueError(f"Repeated batch name '{name}' has an invalid explicit version: {version!r}") from exc
            if normalized in seen:
                raise ValueError(
                    f"Duplicate batch identity '{name}@{normalized}' at inputs {seen[normalized]} and {index}"
                )
            seen[normalized] = index
