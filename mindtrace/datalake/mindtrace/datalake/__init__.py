from .async_datalake import AnnotationSchemaInUseError, AsyncDatalake, DuplicateAnnotationSchemaError
from .datalake import Datalake
from .service import DatalakeService
from .types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    AnnotationSource,
    Asset,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)

__all__ = [
    "AnnotationLabelDefinition",
    "AnnotationRecord",
    "AnnotationSchema",
    "AnnotationSet",
    "AnnotationSource",
    "AnnotationSchemaInUseError",
    "Asset",
    "PascalVocImportConfig",
    "PascalVocImportSummary",
    "AssetRetention",
    "AsyncDatalake",
    "Collection",
    "CollectionItem",
    "DatasetVersion",
    "Datalake",
    "DatalakeService",
    "Datum",
    "DuplicateAnnotationSchemaError",
    "ResolvedCollectionItem",
    "ResolvedDatasetVersion",
    "ResolvedDatum",
    "import_pascal_voc",
    "StorageRef",
    "SubjectRef",
]


def __getattr__(name: str):
    if name in {"PascalVocImportConfig", "PascalVocImportSummary", "import_pascal_voc"}:
        from .importers import PascalVocImportConfig, PascalVocImportSummary, import_pascal_voc

        exports = {
            "PascalVocImportConfig": PascalVocImportConfig,
            "PascalVocImportSummary": PascalVocImportSummary,
            "import_pascal_voc": import_pascal_voc,
        }
        return exports[name]
    raise AttributeError(name)
