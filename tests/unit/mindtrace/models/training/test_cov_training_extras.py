"""Coverage-raising tests for datalake_bridge and ultralytics training extras.

These target previously-uncovered branches:

- ``datalake_bridge``: prefetch path (113, 121-124), ``__len__`` (149) and the
  ``num_workers`` force-to-zero warning branch (223-227).
- ``ultralytics``: the string/path ``_load_yolo`` YOLO import branch (48-52),
  ``_flatten`` non-container return (190), the no-comparable-tensors zero
  return (202-203) and the distillation exception handler (274-275).

Everything runs offline on CPU; heavy deps (ultralytics YOLO) are faked.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.training.datalake_bridge import (  # noqa: E402
    DatalakeDataset,
    build_datalake_loader,
)
from mindtrace.models.training.ultralytics import (  # noqa: E402
    UltralyticsDistiller,
    _distillation_loss,
    _load_yolo,
)


def _datum(id_: int, data: object) -> SimpleNamespace:
    return SimpleNamespace(id=id_, data=data, registry_uri=None, registry_key=None)


# ---------------------------------------------------------------------------
# datalake_bridge: prefetch + __len__
# ---------------------------------------------------------------------------


class TestDatalakePrefetch:
    def test_prefetch_populates_cache_and_len(self):
        rows = [{"image": 1, "label": 10}, {"image": 2, "label": 20}]
        fetched_ids: list[list] = []

        async def query_data(query, datums_wanted=None):
            # Include a MongoDB _id to exercise the strip logic.
            return [{"_id": "abc", **r} for r in rows]

        async def get_data(ids):
            fetched_ids.append(sorted(ids))
            return [_datum(i, f"data-{i}") for i in ids]

        datalake = SimpleNamespace(query_data=query_data, get_data=get_data)
        dataset = DatalakeDataset(
            datalake,
            query={"column": "image"},
            transform=lambda d: (d["image"].data, d["label"].data),
            prefetch=True,
        )

        # __len__ (line 149)
        assert len(dataset) == 2
        # _prefetch_all populated the cache (lines 121-124) with unique ids
        assert set(dataset._cache.keys()) == {1, 2, 10, 20}
        # _id fields were stripped from rows
        assert all("_id" not in row for row in dataset._id_rows)
        # get_data called once with all unique ids (bulk prefetch)
        assert fetched_ids == [[1, 2, 10, 20]]

        # __getitem__ served entirely from cache (no extra fetch)
        image, label = dataset[0]
        assert image == "data-1"
        assert label == "data-10"
        assert fetched_ids == [[1, 2, 10, 20]]

    def test_prefetch_skips_none_ids(self):
        async def query_data(query, datums_wanted=None):
            return [{"image": 1, "label": None}]

        async def get_data(ids):
            # None must have been filtered out before fetch.
            assert None not in ids
            return [_datum(i, f"data-{i}") for i in ids]

        datalake = SimpleNamespace(query_data=query_data, get_data=get_data)
        dataset = DatalakeDataset(
            datalake,
            query={"column": "image"},
            transform=lambda d: (d["image"].data, None),
            prefetch=True,
        )
        assert 1 in dataset._cache
        assert None not in dataset._cache


# ---------------------------------------------------------------------------
# datalake_bridge: build_datalake_loader num_workers force-to-zero warning
# ---------------------------------------------------------------------------


class TestBuildLoaderNumWorkersWarning:
    def test_lazy_with_workers_forces_zero(self):
        fake_dataset = object()
        with patch(
            "mindtrace.models.training.datalake_bridge.DatalakeDataset",
            return_value=fake_dataset,
        ) as mock_ds:
            with patch("torch.utils.data.DataLoader") as mock_loader:
                build_datalake_loader(
                    datalake=SimpleNamespace(),
                    query={"column": "image"},
                    transform=lambda d: (0, 0),
                    prefetch=False,
                    num_workers=4,
                    batch_size=8,
                    shuffle=False,
                )

        # lines 222-227: num_workers coerced to 0
        _, loader_kwargs = mock_loader.call_args
        assert loader_kwargs["num_workers"] == 0
        # dataset built with prefetch=False propagated through
        assert mock_ds.call_args.kwargs["prefetch"] is False


# ---------------------------------------------------------------------------
# ultralytics: _load_yolo string/path branch
# ---------------------------------------------------------------------------


class TestLoadYolo:
    def test_string_path_loads_via_yolo(self):
        constructed: list[str] = []

        class _FakeYOLO:
            def __init__(self, name):
                constructed.append(name)

        fake_module = SimpleNamespace(YOLO=_FakeYOLO)
        with patch.dict(sys.modules, {"ultralytics": fake_module}):
            result = _load_yolo("yolov8n.pt")

        assert isinstance(result, _FakeYOLO)
        assert constructed == ["yolov8n.pt"]

    def test_fspath_object_loads_via_yolo(self):
        import pathlib

        class _FakeYOLO:
            def __init__(self, name):
                self.name = name

        fake_module = SimpleNamespace(YOLO=_FakeYOLO)
        with patch.dict(sys.modules, {"ultralytics": fake_module}):
            result = _load_yolo(pathlib.Path("weights/model.pt"))

        assert isinstance(result, _FakeYOLO)
        assert result.name == str(pathlib.Path("weights/model.pt"))

    def test_import_error_raised_when_ultralytics_missing(self):
        # Simulate ultralytics not being importable.
        with patch.dict(sys.modules, {"ultralytics": None}):
            with pytest.raises(ImportError, match="Ultralytics is required"):
                _load_yolo("yolov8n.pt")

    def test_non_string_model_returned_as_is(self):
        model = object()
        assert _load_yolo(model) is model


# ---------------------------------------------------------------------------
# ultralytics: _distillation_loss edge cases
# ---------------------------------------------------------------------------


class TestDistillationLossEdges:
    def test_non_container_inputs_return_zero_scalar(self):
        # _flatten hits the bare `return []` (line 190) for both, so no
        # comparable tensors exist -> zero scalar with ref None (line 203).
        loss = _distillation_loss(5, "not-a-tensor")
        assert loss.item() == pytest.approx(0.0)
        assert loss.shape == torch.Size([])

    def test_no_matching_shapes_returns_zero_tied_to_student(self):
        # student has a tensor but no teacher tensor matches its shape ->
        # ref is s_tensors[0], hits `ref.sum() * 0.0` (line 202).
        s = torch.ones(2, 2, requires_grad=True)
        t = torch.ones(3, 3)
        loss = _distillation_loss(s, t)
        assert loss.item() == pytest.approx(0.0)
        # gradient path exists (tied to student graph)
        loss.backward()
        assert s.grad is not None


# ---------------------------------------------------------------------------
# ultralytics: distillation callback exception handler
# ---------------------------------------------------------------------------


class _FakeYolo:
    def __init__(self):
        self.callbacks: dict[str, list] = {}
        self.model = torch.nn.Conv2d(3, 4, 3, padding=1)

    def add_callback(self, event, func):
        self.callbacks.setdefault(event, []).append(func)


class TestDistillerExceptionHandler:
    def test_teacher_failure_is_swallowed_and_base_loss_returned(self):
        student = _FakeYolo()

        class _RaisingTeacher(torch.nn.Module):
            def forward(self, x):
                raise RuntimeError("teacher boom")

        teacher = _FakeYolo()
        teacher.model = _RaisingTeacher()

        class _TrainerModel(torch.nn.Module):
            def loss(self, batch, preds=None):
                return torch.tensor(3.0), torch.tensor([1.0])

        trainer_model = _TrainerModel()
        fake_trainer = MagicMock()
        fake_trainer.model = trainer_model

        distiller = UltralyticsDistiller(teacher=teacher, alpha=0.5)
        distiller.attach(student)
        student.callbacks["on_train_start"][0](fake_trainer)

        batch = {"img": torch.zeros(1, 3, 4, 4)}
        # teacher(images) raises -> exception handler (274-275) -> base loss unchanged
        loss, items = trainer_model.loss(batch, preds=torch.zeros(1, 4, 4, 4))
        assert loss.item() == pytest.approx(3.0)
        assert items is not None
