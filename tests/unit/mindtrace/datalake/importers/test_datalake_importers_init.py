import importlib

import pytest


@pytest.mark.parametrize(
    ("export_name", "expected_name"),
    [
        ("Flowers102ImportConfig", "Flowers102ImportConfig"),
        ("Flowers102ImportSummary", "Flowers102ImportSummary"),
        ("import_flowers102", "import_flowers102"),
        ("PascalVocImportConfig", "PascalVocImportConfig"),
        ("PascalVocImportSummary", "PascalVocImportSummary"),
        ("import_pascal_voc", "import_pascal_voc"),
    ],
)
def test_importers_package_lazy_exports_resolve_importer_symbols(export_name, expected_name):
    importers_module = importlib.import_module("mindtrace.datalake.importers")
    module_name = "flowers102" if "Flowers102" in export_name or export_name == "import_flowers102" else "pascal_voc"
    importer_module = importlib.import_module(f"mindtrace.datalake.importers.{module_name}")

    assert getattr(importers_module, export_name) is getattr(importer_module, expected_name)


def test_importers_package_unknown_lazy_export_raises_attribute_error():
    importers_module = importlib.import_module("mindtrace.datalake.importers")

    with pytest.raises(AttributeError, match="UnknownImporterExport"):
        getattr(importers_module, "UnknownImporterExport")
