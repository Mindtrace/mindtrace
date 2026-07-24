__all__ = [
    "Flowers102ImportConfig",
    "Flowers102ImportSummary",
    "PennFudanImportConfig",
    "PennFudanImportSummary",
    "PascalVocImportConfig",
    "PascalVocImportSummary",
    "import_flowers102",
    "import_penn_fudan",
    "import_pascal_voc",
]


def __getattr__(name: str):
    if name in {"Flowers102ImportConfig", "Flowers102ImportSummary", "import_flowers102"}:
        from .flowers102 import Flowers102ImportConfig, Flowers102ImportSummary, import_flowers102

        exports = {
            "Flowers102ImportConfig": Flowers102ImportConfig,
            "Flowers102ImportSummary": Flowers102ImportSummary,
            "import_flowers102": import_flowers102,
        }
        return exports[name]
    if name in {"PascalVocImportConfig", "PascalVocImportSummary", "import_pascal_voc"}:
        from .pascal_voc import PascalVocImportConfig, PascalVocImportSummary, import_pascal_voc

        exports = {
            "PascalVocImportConfig": PascalVocImportConfig,
            "PascalVocImportSummary": PascalVocImportSummary,
            "import_pascal_voc": import_pascal_voc,
        }
        return exports[name]
    if name in {"PennFudanImportConfig", "PennFudanImportSummary", "import_penn_fudan"}:
        from .penn_fudan import PennFudanImportConfig, PennFudanImportSummary, import_penn_fudan

        exports = {
            "PennFudanImportConfig": PennFudanImportConfig,
            "PennFudanImportSummary": PennFudanImportSummary,
            "import_penn_fudan": import_penn_fudan,
        }
        return exports[name]
    raise AttributeError(name)
