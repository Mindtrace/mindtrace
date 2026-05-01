"""Registry tests for 3D scanner service ``TaskSchema`` definitions.

``ALL_SCHEMAS`` keys (e.g. ``get_backends``) are the RPC route names and can differ
from ``TaskSchema.name`` (e.g. ``get_scanner_backends``).
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.scanners_3d.schemas import ALL_SCHEMAS
from mindtrace.hardware.services.scanners_3d.schemas import __all__ as schemas_all

_NO_INPUT_KEYS = frozenset(
    {
        "health",
        "get_backends",
        "get_backend_info",
        "close_all_scanners",
        "get_active_scanners",
        "get_system_diagnostics",
    },
)

_SUBMODULES = (
    "mindtrace.hardware.services.scanners_3d.schemas.capture_schemas",
    "mindtrace.hardware.services.scanners_3d.schemas.config_schemas",
    "mindtrace.hardware.services.scanners_3d.schemas.health_schemas",
    "mindtrace.hardware.services.scanners_3d.schemas.info_schemas",
    "mindtrace.hardware.services.scanners_3d.schemas.lifecycle_schemas",
)


@pytest.mark.parametrize("mod", _SUBMODULES)
def test_schema_submodules_import(mod: str) -> None:
    importlib.import_module(mod)


def test_all_schemas_are_task_schemas_with_output() -> None:
    assert ALL_SCHEMAS
    for key, schema in ALL_SCHEMAS.items():
        assert isinstance(schema, TaskSchema), key
        assert schema.output_schema is not None, key
        assert issubclass(schema.output_schema, BaseModel), key


def test_no_input_schemas_match_registry() -> None:
    no_in = {k for k, s in ALL_SCHEMAS.items() if s.input_schema is None}
    assert no_in == _NO_INPUT_KEYS
    for key, schema in ALL_SCHEMAS.items():
        if key in _NO_INPUT_KEYS:
            assert schema.input_schema is None, key
        else:
            assert schema.input_schema is not None, key
            assert issubclass(schema.input_schema, BaseModel), key


def test_task_names_unique() -> None:
    names = [s.name for s in ALL_SCHEMAS.values()]
    assert len(names) == len(set(names))


def test_public_exports_are_task_schemas() -> None:
    names = [n for n in schemas_all if n != "ALL_SCHEMAS"]
    mod = importlib.import_module("mindtrace.hardware.services.scanners_3d.schemas")
    for n in names:
        assert isinstance(getattr(mod, n), TaskSchema), n
