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
def test_datalake_lazy_exports_resolve_pascal_voc_symbols(export_name, expected_name):
    datalake_module = importlib.import_module("mindtrace.datalake")
    pascal_voc_module = importlib.import_module("mindtrace.datalake.importers.pascal_voc")

    exported = getattr(datalake_module, export_name)
    expected = getattr(pascal_voc_module, expected_name)

    assert exported is expected


def test_datalake_lazy_exports_raise_attribute_error_for_unknown_name():
    datalake_module = importlib.import_module("mindtrace.datalake")

    with pytest.raises(AttributeError, match="NotARealExport"):
        getattr(datalake_module, "NotARealExport")


def test_datalake_exports_sync_symbols():
    datalake_module = importlib.import_module("mindtrace.datalake")

    assert datalake_module.DatasetSyncManager.__name__ == "DatasetSyncManager"
    assert datalake_module.DatasetSyncBundle.__name__ == "DatasetSyncBundle"
    assert datalake_module.DatasetSyncImportRequest.__name__ == "DatasetSyncImportRequest"
    assert datalake_module.DatasetSyncImportPlan.__name__ == "DatasetSyncImportPlan"
    assert datalake_module.DatasetSyncCommitResult.__name__ == "DatasetSyncCommitResult"
    assert datalake_module.DatasetSyncPayloadPlan.__name__ == "DatasetSyncPayloadPlan"
    assert datalake_module.ObjectPayloadDescriptor.__name__ == "ObjectPayloadDescriptor"
    assert datalake_module.MetadataFirstReplicationManager.__name__ == "MetadataFirstReplicationManager"
    assert datalake_module.ReplicatedAssetState.__name__ == "ReplicatedAssetState"
    assert datalake_module.ReplicationBatchRequest.__name__ == "ReplicationBatchRequest"
    assert datalake_module.ReplicationBatchResult.__name__ == "ReplicationBatchResult"
    assert datalake_module.ReplicationReconcileRequest.__name__ == "ReplicationReconcileRequest"
    assert datalake_module.ReplicationReconcileResult.__name__ == "ReplicationReconcileResult"
    assert datalake_module.ReplicationStatusResult.__name__ == "ReplicationStatusResult"
