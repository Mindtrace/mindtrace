import importlib

import pytest


def test_storage_module_lazy_loads_gcs_handler():
    storage_module = importlib.import_module("mindtrace.storage")
    storage_module.__dict__.pop("GCSStorageHandler", None)

    handler = storage_module.GCSStorageHandler

    assert handler.__name__ == "GCSStorageHandler"
    assert storage_module.GCSStorageHandler is handler


def test_storage_module_rejects_unknown_attribute():
    storage_module = importlib.import_module("mindtrace.storage")

    with pytest.raises(AttributeError, match="has no attribute"):
        getattr(storage_module, "NotAStorageSymbol")
