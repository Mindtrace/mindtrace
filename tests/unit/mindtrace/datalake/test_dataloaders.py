import copy
import pickle
from types import SimpleNamespace

import pytest

from mindtrace.models.training import GroupedClassBatchSampler
from mindtrace.models.training import huggingface_dataloaders as dataloaders


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
        self.info = SimpleNamespace(metadata={})
        self._transform = None

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        if self._transform is None:
            return row
        transformed = self._transform({key: [value] for key, value in row.items()})
        return {key: values[0] for key, values in transformed.items()}

    def with_transform(self, transform):
        transformed = copy.copy(self)
        transformed._transform = transform
        return transformed

    def select(self, indices):
        selected = copy.copy(self)
        selected.rows = [self.rows[index] for index in indices]
        return selected

    def filter(self, predicate):
        filtered = copy.copy(self)
        filtered.rows = [row for row in self.rows if predicate(row)]
        return filtered

    def shuffle(self, seed=None):
        shuffled = copy.copy(self)
        shuffled.shuffle_seed = seed
        return shuffled

    def train_test_split(self, **kwargs):
        return {"train": self, "test": copy.copy(self), "kwargs": kwargs}


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

    def bool(self):
        self.dtype = "bool"
        return self

    def to(self, *_args, **_kwargs):
        return self


class _FakeGenerator:
    def manual_seed(self, seed):
        self.seed = seed
        return self


class _FakeTorch:
    bool = "bool"
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
    def stack(tensors):
        return _FakeTensor([tensor.value for tensor in tensors], dtype=tensors[0].dtype)

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

    dataset = dataloaders.build_datasets("/export")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert sample["image"] == ("normalized", image, 255)
    assert image.mode == "RGB"
    assert target.value == 1
    assert target.dtype == "long"
    assert dataset.features["label"].names == ["pink primrose", "orchid"]


def test_multi_label_classification_dataset_returns_float_target(monkeypatch):
    image = _FakeImage()
    labels_feature = SimpleNamespace(feature=SimpleNamespace(names=["aeroplane", "bicycle", "bird"]))
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [{"image": image, "labels": [1.0, 0.0, 1.0], "label_ids": [0, 2]}],
            column_names=["image", "labels", "label_ids"],
            features={"label_ids": labels_feature},
        ),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets("/export")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert sample["image"] == ("normalized", image, 255)
    assert target.value == [1.0, 0.0, 1.0]
    assert target.dtype == "float32"
    assert dataset.features["label_ids"].feature.names == ["aeroplane", "bicycle", "bird"]


def test_classification_dataset_is_picklable_for_spawned_workers(monkeypatch):
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([{"image": _FakeImage(), "label": 1}]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets("/export")["train"]

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

    dataset = dataloaders.build_datasets("/export")["train"]
    with pytest.raises(ValueError, match="include_media=True"):
        dataset[0]


def test_classification_dataloader_collates_native_dataset_mappings(monkeypatch):
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([{"image": _FakeImage(), "label": 0}]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    loader = dataloaders.build_dataloaders("/export")["train"]
    collate_fn = loader.kwargs["collate_fn"]
    image_a = _FakeTensor("image-a", dtype="float32")
    image_b = _FakeTensor("image-b", dtype="float32")
    target_a = _FakeTensor(0, dtype="long")
    target_b = _FakeTensor(1, dtype="long")

    images, targets = collate_fn(
        [
            {"image": image_a, "target": target_a},
            {"image": image_b, "target": target_b},
        ]
    )

    assert images.value == ["image-a", "image-b"]
    assert targets.value == [0, 1]


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

    dataset = dataloaders.build_datasets("/export", task="detection")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert sample["image"] == ("normalized", image, 255)
    assert target["boxes"].value == [[10.0, 20.0, 40.0, 60.0]]
    assert target["boxes"].dtype == "float32"
    assert target["boxes"].shape == (-1, 4)
    assert target["labels"].value == [1]
    assert target["labels"].dtype == "long"
    assert target["area"].value == [1200.0]
    assert target["iscrowd"].value == [0]
    assert "asset_id" not in target
    assert dataset.features["objects"].feature["category"].names == ["aeroplane", "bicycle"]


def test_detection_dataset_can_return_provenance_outside_tensor_target(monkeypatch):
    objects_feature = SimpleNamespace(feature={"category": SimpleNamespace(names=["object"])})
    row = {
        "asset_id": "asset-1",
        "image": _FakeImage(),
        "objects": {
            "bbox": [[1.0, 2.0, 3.0, 4.0]],
            "category": [0],
            "area": [12.0],
        },
    }
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [row],
            column_names=list(row),
            features={"objects": objects_feature},
        ),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets(
        "/export",
        task="detection",
        return_metadata=True,
    )["train"]
    sample = dataset[0]

    assert sample["metadata"] == {"asset_id": "asset-1"}
    assert "asset_id" not in sample["target"]
    assert all(callable(getattr(value, "to", None)) for value in sample["target"].values())


def test_classification_dataset_returns_requested_metadata_keys(monkeypatch):
    row = {
        "asset_id": "asset-1",
        "image": _FakeImage(),
        "label": 1,
        "subject_id": "subject-1",
        "group_id": "group-1",
    }
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row)),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets(
        "/export",
        return_metadata=True,
        metadata_keys=("subject_id", "group_id"),
    )["train"]

    assert dataset[0]["metadata"] == {
        "asset_id": "asset-1",
        "subject_id": "subject-1",
        "group_id": "group-1",
    }


def test_build_datasets_rejects_missing_requested_metadata_key(monkeypatch):
    row = {"asset_id": "asset-1", "image": _FakeImage(), "label": 1}
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row)),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    with pytest.raises(ValueError, match="missing required column.*group_id"):
        dataloaders.build_datasets(
            "/export",
            return_metadata=True,
            metadata_keys=("group_id",),
        )


def test_build_datasets_requires_return_metadata_for_metadata_keys():
    with pytest.raises(ValueError, match="metadata_keys requires return_metadata=True"):
        dataloaders.build_datasets("/export", metadata_keys=("group_id",))


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

    assert isinstance(loaders["train"].dataset, _FakeSplitDataset)
    assert collate_fn(
        [
            {"image": "image-a", "target": {"boxes": "a"}},
            {"image": "image-b", "target": {"boxes": "b"}},
        ]
    ) == (
        ["image-a", "image-b"],
        [{"boxes": "a"}, {"boxes": "b"}],
    )


def test_detection_dataloader_preserves_optional_metadata_column(monkeypatch):
    objects_feature = SimpleNamespace(feature={"category": SimpleNamespace(names=["object"])})
    row = {"asset_id": "asset-1", "image": _FakeImage(), "objects": []}
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [row],
            column_names=list(row),
            features={"objects": objects_feature},
        ),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    loaders = dataloaders.build_dataloaders(
        "/export",
        task="detection",
        return_metadata=True,
    )
    collate_fn = loaders["train"].kwargs["collate_fn"]

    assert collate_fn(
        [
            {"image": "image-a", "target": {"boxes": "a"}, "metadata": {"asset_id": "a"}},
            {"image": "image-b", "target": {"boxes": "b"}, "metadata": {"asset_id": "b"}},
        ]
    ) == (
        ["image-a", "image-b"],
        [{"boxes": "a"}, {"boxes": "b"}],
        [{"asset_id": "a"}, {"asset_id": "b"}],
    )


def test_build_datasets_returns_requested_split_adapters_and_split_transforms(monkeypatch):
    row = {"image": _FakeImage(), "label": 0}
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row]),
        val=_FakeSplitDataset([row]),
        test=_FakeSplitDataset([row]),
    )
    load_calls = []
    dependencies = _dependency_bundle(payload)

    def load_from_disk(path):
        load_calls.append(path)
        return payload

    dependencies[0].load_from_disk = load_from_disk
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: dependencies,
    )

    def train_transform(image):
        return "train", image

    def val_transform(image):
        return "val", image

    datasets = dataloaders.build_datasets(
        "/export",
        splits=("train", "val"),
        transforms={"train": train_transform, "val": val_transform},
    )

    assert tuple(datasets) == ("train", "val")
    assert all(isinstance(dataset, _FakeSplitDataset) for dataset in datasets.values())
    assert datasets["train"][0]["image"] == ("train", row["image"])
    assert datasets["val"][0]["image"] == ("val", row["image"])
    assert datasets["train"].select([0])[0]["target"].dtype == "long"
    assert callable(datasets["train"].filter)
    assert callable(datasets["train"].shuffle)
    assert callable(datasets["train"].train_test_split)
    assert datasets["train"].features is payload["train"].features
    assert load_calls == ["/export"]


def test_semantic_segmentation_dataset_returns_image_and_long_mask(monkeypatch):
    image = _FakeImage()
    mask = _FakeImage()
    row = {
        "asset_id": "voc-1",
        "image": image,
        "mask": mask,
    }
    split = _FakeSplitDataset([row], column_names=list(row), features={})
    split.info = SimpleNamespace(
        metadata={
            "mindtrace": {
                "profile": "semantic_segmentation",
                "class_names": ["background", "person"],
                "background_id": 0,
                "ignore_index": 255,
            }
        }
    )
    payload = _FakeDatasetDict(train=split)
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets("/export", task="semantic_segmentation")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert sample["image"] == ("normalized", image, 255)
    assert image.mode == "RGB"
    assert target.value is mask
    assert target.squeezed_dimension == 0
    assert target.dtype == "long"
    assert dataset.info.metadata["mindtrace"] == {
        "profile": "semantic_segmentation",
        "class_names": ["background", "person"],
        "background_id": 0,
        "ignore_index": 255,
    }


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

    loaders = dataloaders.build_dataloaders("/export", task="segmentation")
    collate_fn = loaders["train"].kwargs["collate_fn"]

    assert isinstance(loaders["train"].dataset, _FakeSplitDataset)
    assert collate_fn(
        [
            {"image": "image-a", "target": "mask-a"},
            {"image": "image-b", "target": "mask-b"},
        ]
    ) == (
        ["image-a", "image-b"],
        ["mask-a", "mask-b"],
    )


@pytest.mark.parametrize("task", ["segmentation", "semantic_segmentation", "semantic-segmentation"])
def test_build_datasets_supports_inferred_and_explicit_semantic_profiles(monkeypatch, task):
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

    datasets = dataloaders.build_datasets("/export", task=task)

    assert isinstance(datasets["train"], _FakeSplitDataset)
    assert datasets["train"][0]["target"].dtype == "long"


@pytest.mark.parametrize("task", ["segmentation", "instance_segmentation", "instance-segmentation"])
def test_build_datasets_supports_inferred_and_explicit_instance_profiles(monkeypatch, task):
    objects_feature = SimpleNamespace(
        feature={"category": SimpleNamespace(names=["background", "person"]), "mask": SimpleNamespace()}
    )
    row = {"asset_id": "instance-1", "image": _FakeImage(), "objects": {"mask": []}}
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row), features={"objects": objects_feature}),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    datasets = dataloaders.build_datasets("/export", task=task)

    assert isinstance(datasets["train"], _FakeSplitDataset)
    assert datasets["train"].features["objects"] is objects_feature


def test_build_datasets_infers_instance_profile_from_reloaded_hf_sequence_schema(monkeypatch):
    objects_feature = {
        "category": SimpleNamespace(feature=SimpleNamespace(names=["background", "person"])),
        "mask": SimpleNamespace(feature=SimpleNamespace()),
    }
    row = {"asset_id": "instance-1", "image": _FakeImage(), "objects": {"mask": []}}
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row), features={"objects": objects_feature}),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    datasets = dataloaders.build_datasets("/export", task="segmentation")

    assert isinstance(datasets["train"], _FakeSplitDataset)
    assert datasets["train"].features["objects"] is objects_feature


def test_instance_segmentation_dataset_returns_mask_rcnn_target(monkeypatch):
    image = _FakeImage()
    mask = _FakeImage()
    objects_feature = SimpleNamespace(
        feature={"category": SimpleNamespace(names=["background", "person"]), "mask": SimpleNamespace()}
    )
    row = {
        "asset_id": "penn-fudan-1",
        "image": image,
        "objects": {
            "mask": [mask],
            "bbox": [[10.0, 20.0, 30.0, 40.0]],
            "category": [1],
            "area": [321.0],
            "iscrowd": [False],
        },
    }
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row), features={"objects": objects_feature}),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets("/export", task="instance_segmentation")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert sample["image"] == ("normalized", image, 255)
    assert target["boxes"].value == [[10.0, 20.0, 40.0, 60.0]]
    assert target["labels"].value == [1]
    assert target["masks"].value == [mask]
    assert target["masks"].dtype == "bool"
    assert target["area"].value == [321.0]
    assert target["iscrowd"].value == [0]
    assert "asset_id" not in target


def test_build_datasets_rejects_ambiguous_segmentation_schema(monkeypatch):
    row = {
        "asset_id": "panoptic-1",
        "image": _FakeImage(),
        "mask": _FakeImage(),
        "objects": {"masks": []},
    }
    objects_feature = SimpleNamespace(feature={"mask": SimpleNamespace()})
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row), features={"objects": objects_feature}),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    with pytest.raises(ValueError, match="ambiguous"):
        dataloaders.build_datasets("/export", task="segmentation")


def test_build_datasets_does_not_treat_detection_objects_as_instance_masks(monkeypatch):
    row = {"asset_id": "detection-1", "image": _FakeImage(), "objects": {"bbox": []}}
    objects_feature = SimpleNamespace(feature={"bbox": SimpleNamespace(), "category": SimpleNamespace()})
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset([row], column_names=list(row), features={"objects": objects_feature}),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    with pytest.raises(ValueError, match="Unable to infer"):
        dataloaders.build_datasets("/export", task="segmentation")


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
        ({"task": "panoptic"}, "task='segmentation'"),
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


def test_build_datasets_rejects_missing_requested_split(monkeypatch):
    payload = _FakeDatasetDict(train=_FakeSplitDataset([]))
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    with pytest.raises(KeyError, match="available"):
        dataloaders.build_datasets("/export", splits=("train", "test"))


def test_detection_target_contains_only_device_movable_values(monkeypatch):
    objects_feature = SimpleNamespace(feature={"category": SimpleNamespace(names=["object"])})
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [
                {
                    "asset_id": "asset-1",
                    "image": _FakeImage(),
                    "objects": {
                        "bbox": [[1.0, 2.0, 3.0, 4.0]],
                        "category": [0],
                        "area": [12.0],
                        "difficult": [False],
                    },
                }
            ],
            column_names=["asset_id", "image", "objects"],
            features={"objects": objects_feature},
        )
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    sample = dataloaders.build_datasets("/export", task="detection")["train"][0]
    target = sample["target"]

    assert target
    assert all(callable(getattr(value, "to", None)) for value in target.values())


def test_detection_target_preserves_voc_difficult_flags(monkeypatch):
    objects_feature = SimpleNamespace(feature={"category": SimpleNamespace(names=["object"])})
    payload = _FakeDatasetDict(
        train=_FakeSplitDataset(
            [
                {
                    "asset_id": "asset-1",
                    "image": _FakeImage(),
                    "objects": {
                        "bbox": [[1.0, 2.0, 3.0, 4.0]],
                        "category": [0],
                        "area": [12.0],
                        "difficult": [True],
                    },
                }
            ],
            column_names=["asset_id", "image", "objects"],
            features={"objects": objects_feature},
        )
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    sample = dataloaders.build_datasets("/export", task="detection")["train"][0]
    target = sample["target"]

    assert target["difficult"].value == [True]
    assert target["iscrowd"].value == [True]
    assert target["iscrowd"].dtype == "long"


def test_build_dataloaders_accepts_explicit_per_split_shuffle_and_drop_last(monkeypatch):
    row = {"image": _FakeImage(), "label": 0}
    payload = _FakeDatasetDict(
        default=_FakeSplitDataset([row]),
        validation=_FakeSplitDataset([row]),
    )
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    loaders = dataloaders.build_dataloaders(
        "/export",
        shuffle_splits={"default"},
        drop_last_splits={"default"},
    )

    assert loaders["default"].kwargs["shuffle"] is True
    assert loaders["default"].kwargs["drop_last"] is True
    assert loaders["validation"].kwargs["shuffle"] is False
    assert loaders["validation"].kwargs["drop_last"] is False


def test_build_dataloaders_forwards_native_dataloader_kwargs(monkeypatch):
    payload = _FakeDatasetDict(train=_FakeSplitDataset([{"image": _FakeImage(), "label": 0}]))
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )
    sampler = object()

    loaders = dataloaders.build_dataloaders(
        "/export",
        dataloader_kwargs={"sampler": sampler},
    )

    assert loaders["train"].kwargs["sampler"] is sampler
    assert loaders["train"].kwargs["shuffle"] is False


def test_build_dataloaders_forwards_grouped_batch_sampler(monkeypatch):
    payload = _FakeDatasetDict(train=_FakeSplitDataset([{"image": _FakeImage(), "label": 0}]))
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )
    batch_sampler = GroupedClassBatchSampler(
        [0, 0, 1, 1],
        ["a", "b", "c", "d"],
        classes_per_batch=2,
        samples_per_class=2,
    )

    loaders = dataloaders.build_dataloaders(
        "/export",
        per_split_dataloader_kwargs={"train": {"batch_sampler": batch_sampler}},
    )

    assert loaders["train"].kwargs["batch_sampler"] is batch_sampler
    for incompatible in ("batch_size", "shuffle", "sampler", "drop_last"):
        assert incompatible not in loaders["train"].kwargs


def test_semantic_dataset_reads_constants_without_decoding_first_sample(monkeypatch):
    class _MetadataOnlySplit(_FakeSplitDataset):
        def __getitem__(self, index):
            raise AssertionError("dataset construction must not decode row zero")

    split = _MetadataOnlySplit(
        [],
        column_names=["asset_id", "background_id", "class_names", "ignore_index", "image", "mask"],
        features={},
    )
    split.info = SimpleNamespace(
        metadata={
            "mindtrace": {
                "profile": "semantic_segmentation",
                "class_names": ["background", "person"],
                "background_id": 0,
                "ignore_index": 255,
            }
        }
    )
    payload = _FakeDatasetDict(train=split)
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )

    dataset = dataloaders.build_datasets("/export", task="semantic_segmentation")["train"]

    assert dataset.info.metadata["mindtrace"] == {
        "profile": "semantic_segmentation",
        "class_names": ["background", "person"],
        "background_id": 0,
        "ignore_index": 255,
    }


def test_build_datasets_dispatches_to_caller_supplied_task_profile(monkeypatch):
    split_dataset = _FakeSplitDataset([{"custom": "value"}], column_names=["custom"], features={})
    payload = _FakeDatasetDict(train=split_dataset)
    monkeypatch.setattr(
        dataloaders,
        "_require_huggingface_dataloader_dependencies",
        lambda: _dependency_bundle(payload),
    )
    calls = []

    def build_custom_profile(dataset, *, split, transform):
        calls.append((dataset, split, transform))
        return "custom-dataset"

    built = dataloaders.build_datasets(
        "/export",
        task="custom",
        task_profiles={"custom": build_custom_profile},
    )

    assert built == {"train": "custom-dataset"}
    assert calls == [(split_dataset, "train", None)]
