from io import BytesIO
from pathlib import Path

import datasets
from PIL import Image

from mindtrace.models.training import build_datasets


def _png_bytes() -> bytes:
    payload = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(payload, format="PNG")
    return payload.getvalue()


def test_voc_difficult_is_preserved_and_projected_to_torchvision_ignore_channel(tmp_path: Path):
    features = datasets.Features(
        {
            "asset_id": datasets.Value("string"),
            "image": datasets.Image(),
            "objects": datasets.Sequence(
                {
                    "bbox": datasets.Sequence(datasets.Value("float32"), length=4),
                    "category": datasets.ClassLabel(names=["person"]),
                    "area": datasets.Value("float32"),
                    "difficult": datasets.Value("bool"),
                }
            ),
        }
    )
    split = datasets.Dataset.from_list(
        [
            {
                "asset_id": "voc-image-1",
                "image": {"bytes": _png_bytes(), "path": "voc-image-1.png"},
                "objects": {
                    "bbox": [[0.0, 0.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]],
                    "category": [0, 0],
                    "area": [1.0, 1.0],
                    "difficult": [True, False],
                },
            }
        ],
        features=features,
    )
    export_path = tmp_path / "voc-detection"
    datasets.DatasetDict({"train": split}).save_to_disk(str(export_path))

    dataset = build_datasets(export_path, task="detection")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert isinstance(dataset, datasets.Dataset)
    assert dataset.features == split.features
    selected = dataset.select([0])
    assert isinstance(selected, datasets.Dataset)
    assert selected[0]["target"]["iscrowd"].tolist() == [1, 0]
    assert target["difficult"].tolist() == [True, False]
    assert target["iscrowd"].tolist() == [1, 0]
