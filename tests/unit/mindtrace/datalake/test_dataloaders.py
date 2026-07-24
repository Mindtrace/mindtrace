import pickle
from types import SimpleNamespace

import pytest

from mindtrace.datalake import dataloaders


class _FakeImage:
    def __init__(self) -> None:
        self.mode = "RGBA"

    def convert(self, mode: str):
        self.mode = mode
        return self


class _FakeSplitDataset:
    def __init__(self, rows, *, column_names=None, features=None):
        self.rows = rows
        self.column_names = column_names or ["image", "label"]
        self.features = features or {"label": SimpleNamespace(names=["pink primrose", "orchid"])}

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


class _FakeDatasetDict(dict):
    pass


class _FakeTensor:
    def __init__(self, value, dtype=None):
        self.value = value
        self.dtype = dtype
        self.ndim = 3
        self.shape = (1, 1, 1)

    def float(self):
        return self

    def div(self, value):
        return ("normalized", self.value, value)

    def reshape(self, *shape):
        self.shape = shape
        return self

    def squeeze(self, dimension):
        self.squeezed_dimension = dimension
        return self

    def long(self):
        self.dtype = "long"
        return self


class _FakeGenerator:
    def manual_seed(self, seed):
        self.seed = seed
        return self


class _FakeTorch:
    float32 = "float32"
    long = "long"
    Generator = _FakeGenerator

    @staticmethod
    def tensor(value, dtype=None):
        return _FakeTensor(value, dtype=dtype)

    @staticmethod
    def zeros(length, dtype=None):
        return _FakeTensor([0] * length, dtype=dtype)

    @staticmethod
    def initial_seed():
        return 7


class _FakeDataLoader:
    def __init__(self, dataset, **kwargs):
        self.dataset = dataset
        self.kwargs = kwargs


def _dependency_bundle(payload):
    datasets_module = SimpleNamespace(load_from_disk=lambda path: payload)
    return datasets_module, _FakeTorch, _FakeDataLoader, lambda image: _FakeTensor(image)


def test_classification_dataset_returns_normalized_image_and_long_target(monkeypatch):
    image = _FakeImage()
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([{"image": image, "label": 1}]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.HuggingFaceClassificationDataset("/export", split="train")
    sample, target = dataset[0]

    assert sample == ("normalized", image, 255)
    assert image.mode == "RGB"
    assert target.value == 1
    assert target.dtype == "long"
    assert dataset.class_names == ("pink primrose", "orchid")


def test_classification_dataset_is_picklable_for_spawned_workers(monkeypatch):
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([{"image": _FakeImage(), "label": 1}]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.HuggingFaceClassificationDataset("/export", split="train")

    pickle.dumps(dataset)


def test_classification_dataset_rejects_export_without_media(monkeypatch):
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([{"image": None, "label": 0}]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.HuggingFaceClassificationDataset("/export", split="train")
    with pytest.raises(ValueError, match="include_media=True"):
        dataset[0]


def test_detection_dataset_returns_xywh_targets_and_zero_based_labels(monkeypatch):
    image = _FakeImage()
    objects_feature = SimpleNamespace(feature={"category": SimpleNamespace(names=["aeroplane", "bicycle"])})
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [
                {
                    "asset_id": "voc-1",
                    "image": image,
                    "objects": {
                        "bbox": [[10.0, 20.0, 30.0, 40.0]],
                        "category": [1],
                        "area": [1200.0],
                    },
                }
            ],
            column_names=["asset_id", "image", "objects"],
            features={"objects": objects_feature},
        ),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.HuggingFaceDetectionDataset("/export", split="train")
    sample, target = dataset[0]

    assert sample == ("normalized", image, 255)
    assert target["boxes"].value == [[10.0, 20.0, 40.0, 60.0]]
    assert target["boxes"].dtype == "float32"
    assert target["boxes"].shape == (-1, 4)
    assert target["labels"].value == [1]
    assert target["labels"].dtype == "long"
    assert target["area"].value == [1200.0]
    assert target["iscrowd"].value == [0]
    assert target["asset_id"] == "voc-1"
    assert dataset.class_names == ("aeroplane", "bicycle")


def test_detection_dataloader_uses_variable_target_collator(monkeypatch):
    objects_feature = SimpleNamespace(feature={"category": SimpleNamespace(names=["object"])})
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [{"asset_id": "asset-1", "image": _FakeImage(), "objects": []}],
            column_names=["asset_id", "image", "objects"],
            features={"objects": objects_feature},
        ),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    loaders = dataloaders.build_dataloaders("/export", task="detection")
    collate_fn = loaders["train"].kwargs["collate_fn"]

    assert isinstance(loaders["train"].dataset, dataloaders.HuggingFaceDetectionDataset)
    assert collate_fn([("image-a", {"boxes": "a"}), ("image-b", {"boxes": "b"})]) == (
        ["image-a", "image-b"],
        [{"boxes": "a"}, {"boxes": "b"}],
    )


def test_semantic_segmentation_dataset_returns_image_and_long_mask(monkeypatch):
    image = _FakeImage()
    mask = _FakeImage()
    row = {
        "asset_id": "voc-1",
        "image": image,
        "mask": mask,
        "class_names": ["background", "person"],
        "background_id": 0,
        "ignore_index": 255,
    }
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [row],
            column_names=list(row),
            features={},
        ),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.HuggingFaceSemanticSegmentationDataset("/export", split="train")
    sample, target = dataset[0]

    assert sample == ("normalized", image, 255)
    assert image.mode == "RGB"
    assert target.value is mask
    assert target.squeezed_dimension == 0
    assert target.dtype == "long"
    assert dataset.class_names == ("background", "person")
    assert dataset.background_id == 0
    assert dataset.ignore_index == 255


def test_semantic_segmentation_dataloader_uses_variable_size_collator(monkeypatch):
    row = {
        "asset_id": "voc-1",
        "image": _FakeImage(),
        "mask": _FakeImage(),
        "class_names": ["background", "person"],
        "background_id": 0,
        "ignore_index": 255,
    }
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row), features={}),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    loaders = dataloaders.build_dataloaders("/export", task="semantic_segmentation")
    collate_fn = loaders["train"].kwargs["collate_fn"]

    assert isinstance(loaders["train"].dataset, dataloaders.HuggingFaceSemanticSegmentationDataset)
    assert collate_fn([("image-a", "mask-a"), ("image-b", "mask-b")]) == (
        ["image-a", "image-b"],
        ["mask-a", "mask-b"],
    )


def test_build_dataloaders_discovers_splits_and_only_shuffles_train(monkeypatch):
    row = {"image": _FakeImage(), "label": 0}
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row]),
        val=_FakeSplitDataset([row]),
        test=_FakeSplitDataset([row]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    loaders = dataloaders.build_dataloaders(
        "/export",
        batch_size=8,
        num_workers=2,
        persistent_workers=True,
        prefetch_factor=3,
        drop_last=True,
        seed=42,
    )

    assert tuple(loaders) == ("train", "val", "test")
    assert loaders["train"].kwargs["shuffle"] is True
    assert loaders["train"].kwargs["drop_last"] is True
    assert loaders["train"].kwargs["generator"].seed == 42
    assert loaders["val"].kwargs["shuffle"] is False
    assert loaders["val"].kwargs["drop_last"] is False
    assert loaders["test"].kwargs["shuffle"] is False
    assert loaders["train"].kwargs["persistent_workers"] is True
    assert loaders["train"].kwargs["prefetch_factor"] == 3


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"format": "coco"}, "format='huggingface'"),
        ({"task": "instance_segmentation"}, "task='semantic_segmentation'"),
        ({"batch_size": 0}, "batch_size"),
        ({"num_workers": -1}, "num_workers"),
        ({"persistent_workers": True}, "requires num_workers"),
        ({"prefetch_factor": 2}, "requires num_workers"),
    ],
)
def test_build_dataloaders_validates_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        dataloaders.build_dataloaders("/export", **kwargs)


def test_build_dataloaders_rejects_missing_requested_split(monkeypatch):
    payload = _FakeDatasetDict(train=_FakeSplitDataset([]))
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    with pytest.raises(KeyError, match="available"):
        dataloaders.build_dataloaders("/export", splits=("train", "test"))
