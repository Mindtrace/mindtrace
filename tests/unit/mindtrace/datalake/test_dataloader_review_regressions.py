"""Regression specifications for unresolved review findings on PR #523.

These tests intentionally describe the desired behavior before the production
fixes are implemented.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import Mock

import pytest

from mindtrace.datalake import dataloaders
from mindtrace.datalake.exporters import huggingface
from mindtrace.datalake.importers import pascal_voc


def test_voc_version_probe_propagates_backend_failures():
    datalake = Mock()
    datalake.get_dataset_version.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        pascal_voc._ensure_dataset_versions_absent(
            datalake,
            {"canonical": "voc"},
            "2012",
        )


def test_voc_asset_creation_is_idempotent_for_interrupted_imports():
    source = inspect.getsource(pascal_voc.import_pascal_voc)

    assert source.count("create_asset_from_object(") > 0
    assert source.count('on_conflict="overwrite"') == source.count("create_asset_from_object(")


def test_voc_single_label_view_reuses_full_image_datums():
    source = inspect.getsource(pascal_voc.import_pascal_voc)
    single_label_version = source.split('version_specs["classification_single_label"] =', 1)[1]

    assert "single_label_manifest.append(region_datum.datum_id)" not in source
    assert "main_manifest" in single_label_version.split("metadata", 1)[0]


def test_huggingface_exports_stream_rows_to_arrow():
    source = inspect.getsource(huggingface)

    assert "Dataset.from_generator" in source
    assert "Dataset.from_list" not in source


def test_huggingface_profiles_share_one_save_pipeline():
    source = inspect.getsource(huggingface)

    assert hasattr(huggingface, "_save_split_rows")
    assert source.count("save_to_disk(") == 1
    assert source.count("ExportResult(") == 1


def test_huggingface_export_does_not_rescan_all_annotations_for_counts():
    source = inspect.getsource(huggingface)

    assert "for item in dataset.items for annotation in item.annotations" not in source


def test_instance_mask_export_avoids_per_pixel_python_lists():
    source = inspect.getsource(huggingface._instance_mask_payload)

    assert ".getdata()" not in source
    assert "binary_values" not in source
    assert "xs:" not in source
    assert "ys:" not in source


def test_generic_loader_dispatch_is_profile_driven_not_format_placeholder():
    build_datasets_parameters = inspect.signature(dataloaders.build_datasets).parameters
    build_dataloaders_parameters = inspect.signature(dataloaders.build_dataloaders).parameters

    assert "format" not in build_datasets_parameters
    assert "format" not in build_dataloaders_parameters
    assert hasattr(dataloaders, "TASK_PROFILES")


def test_torch_dataset_adapters_live_in_models_training():
    repository_root = Path(__file__).resolve().parents[4]
    training_init = repository_root / "mindtrace/models/mindtrace/models/training/__init__.py"
    source = training_init.read_text()

    assert "build_datasets" in source
    assert "build_dataloaders" in source
    assert "HuggingFaceClassificationDataset" in source


def test_obsolete_live_datalake_bridge_is_retired():
    repository_root = Path(__file__).resolve().parents[4]
    training_root = repository_root / "mindtrace/models/mindtrace/models/training"
    training_init_source = (training_root / "__init__.py").read_text()

    assert not (training_root / "datalake_bridge.py").exists()
    assert "DatalakeDataset" not in training_init_source
    assert "build_datalake_loader" not in training_init_source
