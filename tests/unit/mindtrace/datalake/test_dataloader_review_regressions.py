"""Behavioral regression specifications for unresolved review findings on PR #523."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.importers import pascal_voc
from tests.utils.pascal_voc_support import build_tiny_voc_fixture, make_schema_ref


def test_voc_version_probe_propagates_backend_failures():
    datalake = Mock()
    datalake.get_dataset_version.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        pascal_voc._ensure_dataset_versions_absent(
            datalake,
            {"canonical": "voc"},
            "2012",
        )


def test_voc_import_resumes_after_asset_creation_is_interrupted(tmp_path):
    build_tiny_voc_fixture(
        tmp_path,
        include_segmentation=False,
        include_classification=False,
    )
    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = DocumentNotFoundError("missing")
    stored_assets: dict[str, SimpleNamespace] = {}

    def create_asset_from_object(**kwargs):
        name = kwargs["name"]
        if name in stored_assets and kwargs.get("on_conflict") != "overwrite":
            raise RuntimeError(f"asset conflict: {name}")
        return stored_assets.setdefault(name, SimpleNamespace(asset_id="image_asset"))

    interrupted = True

    def create_datum(**_kwargs):
        nonlocal interrupted
        if interrupted:
            interrupted = False
            raise RuntimeError("simulated interruption")
        return SimpleNamespace(datum_id="datum_1")

    datalake.create_asset_from_object.side_effect = create_asset_from_object
    datalake.create_datum.side_effect = create_datum
    datalake.create_annotation_set.return_value = SimpleNamespace(annotation_set_id="set_detection")
    datalake.create_dataset_version.return_value = SimpleNamespace(dataset_version_id="version_1")
    config = pascal_voc.PascalVocImportConfig(
        root_dir=tmp_path,
        split="train",
        dataset_name="tiny-voc",
        tasks=("detection",),
        create_task_versions=False,
        show_progress=False,
    )

    with patch.object(
        pascal_voc,
        "_ensure_voc_schemas",
        return_value={"detection": make_schema_ref("schema_detection")},
    ):
        with pytest.raises(RuntimeError, match="simulated interruption"):
            pascal_voc.import_pascal_voc(datalake, config)
        summary = pascal_voc.import_pascal_voc(datalake, config)

    assert summary.datum_count == 1
    assert len(stored_assets) == 1
    assert datalake.create_dataset_version.call_args.kwargs["manifest"] == ["datum_1"]


def test_voc_single_label_view_reuses_full_image_datum(tmp_path):
    build_tiny_voc_fixture(tmp_path, include_segmentation=False)
    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = DocumentNotFoundError("missing")
    datalake.create_asset_from_object.return_value = SimpleNamespace(asset_id="image_asset")
    datalake.create_datum.side_effect = lambda **_kwargs: SimpleNamespace(
        datum_id=f"datum_{datalake.create_datum.call_count}"
    )
    datalake.create_annotation_set.side_effect = lambda **_kwargs: SimpleNamespace(
        annotation_set_id=f"set_{datalake.create_annotation_set.call_count}"
    )
    datalake.create_dataset_version.side_effect = lambda **_kwargs: SimpleNamespace(
        dataset_version_id=f"version_{datalake.create_dataset_version.call_count}"
    )
    schemas = {
        "classification": make_schema_ref("schema_classification"),
        "detection": make_schema_ref("schema_detection"),
    }

    with patch.object(pascal_voc, "_ensure_voc_schemas", return_value=schemas):
        summary = pascal_voc.import_pascal_voc(
            datalake,
            pascal_voc.PascalVocImportConfig(
                root_dir=tmp_path,
                split="train",
                dataset_name="tiny-voc",
                tasks=("classification", "detection"),
                show_progress=False,
            ),
        )

    version_calls = {
        call.kwargs["dataset_name"]: call.kwargs for call in datalake.create_dataset_version.call_args_list
    }
    assert datalake.create_datum.call_count == 1
    assert summary.derived_datum_count == 0
    assert version_calls["tiny-voc-classification-single-label"]["manifest"] == ["datum_1"]


def test_torch_dataset_adapters_are_public_from_models_training():
    training = importlib.import_module("mindtrace.models.training")

    assert callable(getattr(training, "build_datasets"))
    assert callable(getattr(training, "build_dataloaders"))
    assert getattr(training, "HuggingFaceClassificationDataset") is not None


def test_obsolete_live_datalake_bridge_is_not_public():
    training = importlib.import_module("mindtrace.models.training")

    assert "DatalakeDataset" not in training.__all__
    assert "build_datalake_loader" not in training.__all__
    assert not hasattr(training, "DatalakeDataset")
    assert not hasattr(training, "build_datalake_loader")
