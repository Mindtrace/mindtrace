"""Real-HF regression coverage for in-memory export cache behaviour."""

import datasets
import pytest

from mindtrace.datalake.exporters.huggingface import _save_huggingface_rows
from mindtrace.datalake.exporters.types import ExportableDataset


@pytest.mark.parametrize("split_names", [("default",), ("train", "val")])
def test_save_huggingface_rows_preserves_data_without_generator_cache(tmp_path, monkeypatch, split_names):
    cache = tmp_path / "hf-cache"
    cache.mkdir()
    monkeypatch.setattr(datasets.config, "HF_DATASETS_CACHE", cache)
    monkeypatch.setenv("HF_DATASETS_CACHE", str(cache))
    features = datasets.Features(
        {
            "asset_id": datasets.Value("string"),
            "payload": datasets.Value("binary"),
            "label": datasets.ClassLabel(names=["a", "b"]),
        }
    )
    rows = {name: [{"asset_id": name, "payload": b"embedded-media", "label": 1}] for name in split_names}
    destination = tmp_path / "artifact"
    _save_huggingface_rows(
        datasets,
        ExportableDataset(name="cache-regression"),
        rows,
        destination=destination,
        features=features,
        asset_count=len(split_names),
        annotation_count=len(split_names),
    )

    restored = datasets.load_from_disk(str(destination))
    for name in split_names:
        split = restored if name == "default" else restored[name]
        assert split.features == features
        assert split[0] == rows[name][0]
    assert not list(cache.rglob("*.arrow"))
