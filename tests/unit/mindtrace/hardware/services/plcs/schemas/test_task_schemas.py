"""Unit tests for PLC service ``TaskSchema`` registry wiring.

These schemas are declarative bindings (task name → Pydantic input/output types).
This suite checks registry consistency and imports only; it does **not** exercise
``PLCManagerService`` behavior, device I/O, or connection logic—those layers remain
out of scope here deliberately.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.plcs.schemas import ALL_SCHEMAS
from mindtrace.hardware.services.plcs.schemas import __all__ as schemas_package_all

# Tasks defined with ``input_schema=None`` in the schema modules.
_EXPECTED_NO_INPUT: frozenset[str] = frozenset(
    {
        "health",
        "discover_backends",
        "get_backend_info",
        "disconnect_all_plcs",
        "get_active_plcs",
        "get_system_diagnostics",
    }
)


SUBMODULES = (
    "mindtrace.hardware.services.plcs.schemas.backend_schemas",
    "mindtrace.hardware.services.plcs.schemas.health_schemas",
    "mindtrace.hardware.services.plcs.schemas.lifecycle_schemas",
    "mindtrace.hardware.services.plcs.schemas.status_schemas",
    "mindtrace.hardware.services.plcs.schemas.tag_schemas",
)


@pytest.mark.parametrize("module", SUBMODULES)
def test_submodules_import_cleanly(module: str) -> None:
    importlib.import_module(module)


def test_all_schemas_dict_matches_declared_task_names() -> None:
    assert ALL_SCHEMAS, "ALL_SCHEMAS must not be empty"
    for key, schema in ALL_SCHEMAS.items():
        assert isinstance(schema, TaskSchema)
        assert schema.name == key, f"registry key {key!r} must match TaskSchema.name {schema.name!r}"


def test_all_schemas_have_output_model() -> None:
    for key, schema in ALL_SCHEMAS.items():
        assert schema.output_schema is not None, f"{key!r} must declare output_schema"
        assert issubclass(schema.output_schema, BaseModel), f"{key!r} output_schema must be a Pydantic model"


def test_input_schema_presence_matches_expected() -> None:
    for key, schema in ALL_SCHEMAS.items():
        if key in _EXPECTED_NO_INPUT:
            assert schema.input_schema is None, f"{key!r} is documented as having no input schema"
        else:
            assert schema.input_schema is not None, f"{key!r} must declare input_schema"
            assert issubclass(schema.input_schema, BaseModel), f"{key!r} input_schema must be a Pydantic model"


def test_expected_no_input_set_is_exhaustive() -> None:
    """Fails if a no-input task is added in code but not listed here (or vice versa)."""
    no_input_in_code = {k for k, s in ALL_SCHEMAS.items() if s.input_schema is None}
    assert no_input_in_code == _EXPECTED_NO_INPUT


def test_no_duplicate_task_names() -> None:
    names = [s.name for s in ALL_SCHEMAS.values()]
    assert len(names) == len(set(names))


def test_public_exports_include_all_schema_constants_except_registry() -> None:
    """``__all__`` lists symbols for star-imports; ALL_SCHEMAS is the aggregate registry."""
    exported = set(schemas_package_all)
    assert "ALL_SCHEMAS" in exported
    exported.discard("ALL_SCHEMAS")
    for name in exported:
        value: Any = getattr(importlib.import_module("mindtrace.hardware.services.plcs.schemas"), name)
        assert isinstance(value, TaskSchema), f"{name} should be a TaskSchema instance"
