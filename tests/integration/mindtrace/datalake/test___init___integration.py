import importlib

import pytest

from mindtrace.datalake.importers.flowers102 import Flowers102ImportConfig, Flowers102ImportSummary
from mindtrace.datalake.importers.pascal_voc import PascalVocImportConfig, PascalVocImportSummary


@pytest.mark.parametrize(
    ("export_name", "expected"),
    [
        ("Flowers102ImportConfig", Flowers102ImportConfig),
        ("Flowers102ImportSummary", Flowers102ImportSummary),
        ("PascalVocImportConfig", PascalVocImportConfig),
        ("PascalVocImportSummary", PascalVocImportSummary),
    ],
)
def test_datalake_package_exports_importer_types(export_name, expected):
    datalake_module = importlib.import_module("mindtrace.datalake")

    assert getattr(datalake_module, export_name) is expected


def test_datalake_package_exports_pascal_voc_import_function():
    datalake_module = importlib.import_module("mindtrace.datalake")
    pascal_voc_module = importlib.import_module("mindtrace.datalake.importers.pascal_voc")

    assert datalake_module.import_pascal_voc is pascal_voc_module.import_pascal_voc


def test_datalake_package_exports_flowers102_import_function():
    datalake_module = importlib.import_module("mindtrace.datalake")
    flowers102_module = importlib.import_module("mindtrace.datalake.importers.flowers102")

    assert datalake_module.import_flowers102 is flowers102_module.import_flowers102


def test_datalake_package_unknown_lazy_export_still_raises_attribute_error():
    datalake_module = importlib.import_module("mindtrace.datalake")

    with pytest.raises(AttributeError, match="DefinitelyMissingExport"):
        getattr(datalake_module, "DefinitelyMissingExport")
