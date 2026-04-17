__all__ = [
    "PascalVocImportConfig",
    "PascalVocImportSummary",
    "import_pascal_voc",
]


def __getattr__(name: str):
    if name in __all__:
        from .pascal_voc import PascalVocImportConfig, PascalVocImportSummary, import_pascal_voc

        exports = {
            "PascalVocImportConfig": PascalVocImportConfig,
            "PascalVocImportSummary": PascalVocImportSummary,
            "import_pascal_voc": import_pascal_voc,
        }
        return exports[name]
    raise AttributeError(name)
