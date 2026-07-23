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
    column_names = ["image", "label"]
    features = {"label": SimpleNamespace(names=["pink primrose", "orchid"])}

    def __init__(self, rows):
        self.rows = rows

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

    def float(self):
        return self

    def div(self, value):
        return ("normalized", self.value, value)


class _FakeGenerator:
    def manual_seed(self, seed):
        self.seed = seed
        return self


class _FakeTorch:
    long = "long"
    Generator = _FakeGenerator

    @staticmethod
    def tensor(value, dtype=None):
        return _FakeTensor(value, dtype=dtype)

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
        ({"task": "detection"}, "task='classification'"),
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
