"""Regression coverage for the training data adapters' public API."""

import importlib


def test_native_huggingface_dataset_builders_are_public_from_models_training():
    training = importlib.import_module("mindtrace.models.training")

    assert callable(getattr(training, "build_datasets"))
    assert callable(getattr(training, "build_dataloaders"))
    assert "HuggingFaceClassificationDataset" not in training.__all__
    assert not hasattr(training, "HuggingFaceClassificationDataset")


def test_obsolete_live_datalake_bridge_is_not_public():
    training = importlib.import_module("mindtrace.models.training")

    assert "DatalakeDataset" not in training.__all__
    assert "build_datalake_loader" not in training.__all__
    assert not hasattr(training, "DatalakeDataset")
    assert not hasattr(training, "build_datalake_loader")
