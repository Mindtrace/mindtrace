from .async_datalake import AnnotationSchemaInUseError, AsyncDatalake, DuplicateAnnotationSchemaError
from .datalake import Datalake
from .replication import ReplicationManager
from .replication_types import (
    ReplicatedAssetState,
    ReplicationBatchRequest,
    ReplicationBatchResult,
    ReplicationReclaimRequest,
    ReplicationReclaimResult,
    ReplicationReconcileRequest,
    ReplicationReconcileResult,
    ReplicationStatusResult,
)
from .service import DatalakeService
from .sync import DatasetSyncManager
from .sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncImportRequest,
    DatasetSyncPayloadPlan,
    ObjectPayloadDescriptor,
)
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
    DirectUploadSession,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from .upload_client import DatalakeDirectUploadClient

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
    "DatasetSyncBundle",
    "DatasetSyncCommitResult",
    "DatasetSyncImportPlan",
    "DatasetSyncImportRequest",
    "DatasetSyncManager",
    "DatasetSyncPayloadPlan",
    "ReplicationManager",
    "ReplicatedAssetState",
    "ReplicationBatchRequest",
    "ReplicationBatchResult",
    "ReplicationReclaimRequest",
    "ReplicationReclaimResult",
    "ReplicationReconcileRequest",
    "ReplicationReconcileResult",
    "ReplicationStatusResult",
    "DatasetVersion",
    "DatalakeDirectUploadClient",
    "Datalake",
    "DatalakeService",
    "DirectUploadSession",
    "Datum",
    "DuplicateAnnotationSchemaError",
    "ResolvedCollectionItem",
    "ResolvedDatasetVersion",
    "ResolvedDatum",
    "import_pascal_voc",
    "ObjectPayloadDescriptor",
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
