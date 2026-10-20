import json

import datasets
import pytest
from PIL import Image

from mindtrace.models.training import build_datasets, read_export_metadata


@pytest.mark.parametrize("legacy_layout", [True, False], ids=["legacy-nested", "flat"])
def test_export_metadata_preserves_native_dataset_operations(tmp_path, legacy_layout):
    """Artifact metadata must not invalidate Hugging Face's DatasetInfo copies."""
    metadata = {
        "profile": "semantic_segmentation",
        "class_names": ["background", "object"],
        "background_id": 0,
        "ignore_index": 255,
    }
    split = datasets.Dataset.from_dict(
        {
            "asset_id": [f"image-{index}" for index in range(4)],
            "image": [Image.new("RGB", (2, 2), color="white") for _ in range(4)],
            "mask": [Image.new("L", (2, 2), color=1) for _ in range(4)],
        },
        features=datasets.Features(
            {"asset_id": datasets.Value("string"), "image": datasets.Image(), "mask": datasets.Image()}
        ),
    )
    export_path = tmp_path / "export"
    datasets.DatasetDict({"train": split}).save_to_disk(str(export_path))
    payload = {"schema_version": 1, "mindtrace": metadata} if legacy_layout else {"schema_version": 2, **metadata}
    (export_path / "mindtrace_metadata.json").write_text(json.dumps(payload), encoding="utf-8")

    dataset = build_datasets(export_path, task="semantic_segmentation")["train"]
    selected = dataset.select([0, 2])
    shuffled = dataset.shuffle(seed=7)
    filtered = dataset.filter(lambda row: bool(row["target"].eq(1).all()), load_from_cache_file=False)
    partitions = dataset.train_test_split(test_size=0.5, seed=7)

    assert len(selected) == 2
    assert len(shuffled) == len(filtered) == 4
    assert len(partitions["train"]) == len(partitions["test"]) == 2
    for derived in (selected, shuffled, filtered, partitions["train"], partitions["test"]):
        assert isinstance(derived, datasets.Dataset)
        assert derived.features == split.features
        assert derived.info.copy().features == split.features
        assert derived[0]["target"].tolist() == [[1, 1], [1, 1]]
        assert not hasattr(derived.info, "metadata")
    assert read_export_metadata(export_path) == metadata
