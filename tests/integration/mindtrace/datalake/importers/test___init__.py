import importlib

import pytest


@pytest.mark.parametrize(
    ("export_name", "expected_name"),
    [
        ("PascalVocImportConfig", "PascalVocImportConfig"),
        ("PascalVocImportSummary", "PascalVocImportSummary"),
        ("import_pascal_voc", "import_pascal_voc"),
    ],
)
def test_importers_package_lazy_exports_resolve_pascal_voc_symbols(export_name, expected_name):
    importers_module = importlib.import_module("mindtrace.datalake.importers")
    pascal_voc_module = importlib.import_module("mindtrace.datalake.importers.pascal_voc")

    assert getattr(importers_module, export_name) is getattr(pascal_voc_module, expected_name)


def test_importers_package_unknown_lazy_export_raises_attribute_error():
    importers_module = importlib.import_module("mindtrace.datalake.importers")

    with pytest.raises(AttributeError, match="UnknownImporterExport"):
        getattr(importers_module, "UnknownImporterExport")
