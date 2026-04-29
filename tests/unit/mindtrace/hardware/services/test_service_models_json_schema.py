"""Smoke-test Pydantic JSON schemas for hardware service API models (Tier A coverage)."""

from __future__ import annotations

import importlib

import pytest
from pydantic import BaseModel

_MODEL_PACKAGES = (
    "mindtrace.hardware.services.scanners_3d.models",
    "mindtrace.hardware.services.stereo_cameras.models",
    "mindtrace.hardware.services.cameras.models",
    "mindtrace.hardware.services.plcs.models",
)


@pytest.mark.parametrize("pkg", _MODEL_PACKAGES)
def test_exported_models_build_json_schema(pkg: str) -> None:
    mod = importlib.import_module(pkg)
    for name in mod.__all__:
        obj = getattr(mod, name)
        if not isinstance(obj, type):
            continue
        try:
            is_model = issubclass(obj, BaseModel)
        except TypeError:
            continue
        if is_model:
            obj.model_json_schema()
