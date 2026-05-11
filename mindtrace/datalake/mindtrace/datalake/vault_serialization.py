"""Conventions for registry ``class`` / ``materializer`` hints on :class:`~mindtrace.datalake.types.Asset`.

These hints let a :class:`~mindtrace.datalake.DataVault` client that only receives **bytes** from a
remote ``objects.get``-style API reconstruct a Python value using the same ZenML materializers as
:class:`~mindtrace.registry.Registry`, provided the payload matches a **single-file** staged layout
(see :meth:`~mindtrace.registry.Registry.materialize_from_bytes`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Type

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.datalake.types import Asset
from mindtrace.registry import Registry

SERIALIZATION_METADATA_KEY = "mindtrace.serialization"

BYTES_MATERIALIZER = "zenml.materializers.BytesMaterializer"
BYTES_CLASS = "builtins.bytes"
DEFAULT_BYTES_FILES = ("data.txt",)


def direct_bytes_serialization_block(
    *,
    init_params: dict[str, Any] | None = None,
    files: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Metadata aligned with :meth:`mindtrace.registry.core._registry_core._RegistryCore._build_direct_bytes_metadata`."""
    return {
        "class": BYTES_CLASS,
        "materializer": BYTES_MATERIALIZER,
        "init_params": dict(init_params or {}),
        "_files": list(files or DEFAULT_BYTES_FILES),
    }


def serialization_block_for_save(
    obj: Any,
    *,
    registry: Registry | None,
    materializer: Type[BaseMaterializer] | None = None,
) -> dict[str, Any]:
    """Build the ``mindtrace.serialization`` payload for an object about to be stored."""
    if isinstance(obj, (bytes, bytearray, Path)):
        return direct_bytes_serialization_block()
    if registry is None:
        raise ValueError(
            "Storing a non-bytes object through DataVault requires ``registry=...`` on the vault (or pass "
            "``asset_metadata`` with a pre-filled ``mindtrace.serialization`` block)."
        )
    hints = registry.serialization_hints_for_object(obj, materializer=materializer)
    return {**hints, "init_params": {}}


def augment_asset_metadata_for_vault_save(
    obj: Any,
    asset_metadata: dict[str, Any] | None,
    *,
    registry: Registry | None,
    materializer: Type[BaseMaterializer] | None = None,
) -> dict[str, Any]:
    """Merge auto serialization hints into ``asset_metadata`` unless the user already set the key."""
    merged = dict(asset_metadata or {})
    if SERIALIZATION_METADATA_KEY in merged:
        return merged
    merged[SERIALIZATION_METADATA_KEY] = serialization_block_for_save(
        obj,
        registry=registry,
        materializer=materializer,
    )
    return merged


def extract_serialization_block(asset: Asset) -> dict[str, Any] | None:
    """Return the serialization dict from an asset, or ``None`` if missing or invalid."""
    block = asset.metadata.get(SERIALIZATION_METADATA_KEY)
    if not isinstance(block, dict):
        return None
    if "class" not in block or "materializer" not in block:
        return None
    return block


def materialize_payload_with_hints(
    registry: Registry,
    raw: bytes | bytearray,
    serialization: dict[str, Any],
    **materializer_kwargs: Any,
) -> Any:
    """Decode *raw* using *serialization* hints and :meth:`~mindtrace.registry.Registry.materialize_from_bytes`.

    Only **single-file** ZenML layouts are supported here; multi-file artifacts require an in-process
    :meth:`~mindtrace.registry.Registry.load` against the backing registry.
    """
    files = serialization.get("_files")
    if isinstance(files, list) and files and all(isinstance(x, str) for x in files):
        rel_paths = list(files)
    else:
        rel_paths = list(DEFAULT_BYTES_FILES)

    if len(rel_paths) > 1:
        raise NotImplementedError(
            "Materializing multi-file ZenML artifacts from a single byte payload is not implemented."
        )

    init_params = serialization.get("init_params") or {}
    if not isinstance(init_params, dict):
        init_params = {}

    return registry.materialize_from_bytes(
        raw,
        object_class=serialization["class"],
        materializer=serialization["materializer"],
        init_params=init_params,
        relative_path=rel_paths[0],
        **materializer_kwargs,
    )
