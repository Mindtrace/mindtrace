"""Coverage-focused unit tests for mindtrace.models.optimization.runner.

Targets uncovered guard/error/helper branches: optional-dep ImportError guards,
on_violation/task validation, default work_dir under TEMP_DIR, prune-after-export
guard, torch-domain rollback, detection-adapter gating branch, final-gate failure
handling, magnitude-prune branch, finetune/QAT guards, detection finetune,
_train_classification loss defaults, quantize guards + detection calibration
feeds, _resolve_num_classes / _infer_input_shape / _first_batch helpers, and
_final_gates torch/openvino runtimes plus tracker logging.

Everything runs offline on CPU with tiny nn.Linear stand-ins; heavy training and
onnx-eval paths are mocked.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402

from mindtrace.models.optimization import (  # noqa: E402
    Export,
    Finetune,
    OptimizationRecipe,
    OptimizationRunner,
    Prune,
    QAT,
    Quantize,
)
from mindtrace.models.optimization import runner as runner_module  # noqa: E402
from mindtrace.models.optimization.runner import (  # noqa: E402
    OnnxModelAdapter,
    _DetectionOnnxAdapter,
)

D = 4
C = 4


def _linear_model() -> nn.Module:
    return nn.Sequential(nn.Linear(D, C))


def _loader(n: int = 8, bs: int = 4) -> DataLoader:
    g = torch.Generator().manual_seed(0)
    x = torch.randn(n, D, generator=g)
    y = torch.randint(0, C, (n,), generator=g)
    return DataLoader(TensorDataset(x, y), batch_size=bs)


def _det_loader():
    """One batch: (list-of-[C,H,W] images, list-of-target-dicts)."""
    imgs = [torch.rand(3, 8, 8), torch.rand(3, 8, 8)]
    tgts = [
        {"boxes": torch.tensor([[0.0, 0.0, 1.0, 1.0]]), "labels": torch.tensor([1])},
        {"boxes": torch.tensor([[0.0, 0.0, 1.0, 1.0]]), "labels": torch.tensor([1])},
    ]
    return [(imgs, tgts)]


def _export_onnx(tmp_path) -> "object":
    """Produce a real .onnx artifact via a static-shape export run."""
    result = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export(static_shape=(1, D))]),
        work_dir=tmp_path,
    ).run()
    return result.artifact_path


# ---------------------------------------------------------------------------
# Optional-dependency ImportError guards (142, 197-198)
# ---------------------------------------------------------------------------


def test_onnx_adapter_import_guard(monkeypatch):
    monkeypatch.setattr(runner_module, "_ORT_AVAILABLE", False)
    with pytest.raises(ImportError):
        OnnxModelAdapter("nope.onnx")


def test_detection_adapter_import_guard(monkeypatch):
    monkeypatch.setattr(runner_module, "_ORT_AVAILABLE", False)
    with pytest.raises(ImportError):
        _DetectionOnnxAdapter("nope.onnx")


# ---------------------------------------------------------------------------
# Adapter real __init__, to/eval, numpy __call__ (167, 196-207)
# ---------------------------------------------------------------------------


def test_onnx_adapter_call_with_numpy_input(tmp_path):
    path = _export_onnx(tmp_path)
    adapter = OnnxModelAdapter(path)
    out = adapter(np.zeros((2, D), dtype=np.float32))  # numpy path, not torch tensor
    assert out.shape == (2, C)


def test_detection_adapter_init_and_noop_moves(tmp_path):
    path = _export_onnx(tmp_path)
    adapter = _DetectionOnnxAdapter(path)  # real __init__ over a real onnx session
    assert adapter.to("cpu") is adapter
    assert adapter.eval() is adapter


# ---------------------------------------------------------------------------
# Constructor validation (295, 297, 325-327)
# ---------------------------------------------------------------------------


def test_invalid_on_violation_rejected():
    with pytest.raises(ValueError, match="on_violation"):
        OptimizationRunner(_linear_model(), OptimizationRecipe(steps=[Export()]), on_violation="bad")


def test_invalid_task_rejected():
    with pytest.raises(ValueError, match="task must be one of"):
        OptimizationRunner(_linear_model(), OptimizationRecipe(steps=[Export()]), task="bogus")


def test_default_work_dir_under_temp_dir():
    runner = OptimizationRunner(_linear_model(), OptimizationRecipe(steps=[Export()]))
    temp_base = str(runner.config.MINDTRACE_DIR_PATHS.TEMP_DIR)
    assert str(runner.work_dir).startswith(temp_base)
    assert runner.work_dir.exists()
    assert "mindtrace-opt-" in runner.work_dir.name


# ---------------------------------------------------------------------------
# Domain / rollback branches (376, 416, 431, 469-472)
# ---------------------------------------------------------------------------


def test_prune_after_export_raises(tmp_path):
    recipe = OptimizationRecipe(steps=[Export(static_shape=(1, D)), Prune(method="magnitude")])
    with pytest.raises(ValueError, match="requires the torch domain"):
        OptimizationRunner(_linear_model(), recipe, work_dir=tmp_path).run()


def test_torch_domain_rollback(tmp_path, monkeypatch):
    metrics = iter([0.9, 0.4])
    monkeypatch.setattr(
        runner_module.OptimizationRunner, "_measure_metric", lambda self, model_like: next(metrics)
    )
    result = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Prune(method="magnitude", sparsity=0.2)]),
        eval_loader=_loader(),
        constraints={"max_accuracy_drop": 0.05},
        on_violation="rollback",
        work_dir=tmp_path,
    ).run()
    assert result.history[0]["rolled_back"] is True
    assert result.violations[0]["step"] == 0


def test_detection_gating_uses_detection_adapter(tmp_path, monkeypatch):
    art1 = tmp_path / "export.onnx"
    art1.write_bytes(b"x")
    art2 = tmp_path / "quant.onnx"
    art2.write_bytes(b"y")

    seen = {}

    class _StubAdapter:
        def __init__(self, path):
            seen["path"] = path

    monkeypatch.setattr(runner_module, "_DetectionOnnxAdapter", _StubAdapter)

    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export(static_shape=(1, 3, 8, 8)), Quantize(mode="dynamic")]),
        eval_loader=_det_loader(),
        task="detection",
        num_classes=2,
        constraints={"max_accuracy_drop": 0.5},
        work_dir=tmp_path,
    )
    metrics = iter([0.9, 0.89])
    runner._measure_metric = lambda model_like: next(metrics)
    runner._export_step = lambda step, index, implicit=False: art1
    runner._quantize_step = lambda step, index, artifact: art2

    result = runner.run()
    # The onnx-domain lossy step routed through the detection adapter branch.
    assert seen["path"] == art2
    assert [h["op"] for h in result.history] == ["export", "quantize"]


def test_final_gate_failure_recorded(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export(static_shape=(1, D))]),
        work_dir=tmp_path,
    )

    def _boom(domain, artifact, violations):
        raise RuntimeError("bench exploded")

    runner._final_gates = _boom
    result = runner.run()
    assert result.report is None
    assert any(v.get("step") == "final_gates" for v in result.violations)


# ---------------------------------------------------------------------------
# Step execution guards / branches
# ---------------------------------------------------------------------------


def test_magnitude_prune_and_torch_final_gates(tmp_path):
    """magnitude branch (499-501) + torch-runtime final gate + p95 violation (842-843, 865)."""
    result = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Prune(method="magnitude", sparsity=0.2)]),
        eval_loader=_loader(),
        constraints={"p95_latency_ms": 1e-12, "max_size_mb": 1000.0},
        work_dir=tmp_path,
    ).run()
    assert result.report is not None
    assert result.report.runtime == "torch"
    assert result.artifact_path.suffix == ".pt"
    assert any(v.get("constraint") == "p95_latency_ms" for v in result.violations)


def test_finetune_requires_train_loader(tmp_path):
    runner = OptimizationRunner(
        _linear_model(), OptimizationRecipe(steps=[Finetune()]), work_dir=tmp_path
    )
    with pytest.raises(ValueError, match="finetune.*train_loader"):
        runner._finetune_step(Finetune())


def test_detection_finetune_with_optimizer_factory(tmp_path, monkeypatch):
    calls = {}

    class _FakeDetTrainer:
        def __init__(self, model, *, num_classes, optimizer, tracker=None):
            calls["num_classes"] = num_classes
            calls["optimizer"] = optimizer

        def fit(self, loader, *, epochs):
            calls["epochs"] = epochs

    monkeypatch.setattr("mindtrace.models.training.DetectionTrainer", _FakeDetTrainer)

    sentinel_opt = object()
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Finetune()]),
        train_loader=_det_loader(),
        task="detection",
        num_classes=3,
        optimizer_factory=lambda m, lr: sentinel_opt,
        work_dir=tmp_path,
    )
    runner._finetune_step(Finetune(epochs=2, lr=1e-3))
    assert calls["optimizer"] is sentinel_opt
    assert calls["num_classes"] == 3
    assert calls["epochs"] == 2


def test_detection_finetune_default_optimizer(tmp_path, monkeypatch):
    calls = {}

    class _FakeDetTrainer:
        def __init__(self, model, *, num_classes, optimizer, tracker=None):
            calls["optimizer"] = optimizer

        def fit(self, loader, *, epochs):
            calls["epochs"] = epochs

    monkeypatch.setattr("mindtrace.models.training.DetectionTrainer", _FakeDetTrainer)

    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Finetune()]),
        train_loader=_det_loader(),
        task="detection",
        work_dir=tmp_path,
    )
    runner._finetune_step(Finetune(epochs=1, lr=1e-3))
    assert isinstance(calls["optimizer"], torch.optim.AdamW)


class _FakeTrainer:
    last = None

    def __init__(self, model, loss_fn, optimizer, *, tracker=None):
        _FakeTrainer.last = {"loss_fn": loss_fn, "optimizer": optimizer}

    def fit(self, train_loader, val_loader, *, epochs):
        _FakeTrainer.last["epochs"] = epochs


def _runner_for_train(tmp_path, **kwargs) -> OptimizationRunner:
    return OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Finetune()]),
        train_loader=_loader(),
        eval_loader=_loader(),
        work_dir=tmp_path,
        **kwargs,
    )


def test_train_classification_explicit_loss_fn(tmp_path, monkeypatch):
    monkeypatch.setattr("mindtrace.models.training.Trainer", _FakeTrainer)
    my_loss = nn.L1Loss()
    runner = _runner_for_train(tmp_path, loss_fn=my_loss)
    runner._train_classification(epochs=1, lr=0.1)
    assert _FakeTrainer.last["loss_fn"] is my_loss


def test_train_classification_regression_defaults_mse(tmp_path, monkeypatch):
    monkeypatch.setattr("mindtrace.models.training.Trainer", _FakeTrainer)
    runner = _runner_for_train(tmp_path, task="regression")
    runner._train_classification(epochs=1, lr=0.1)
    assert isinstance(_FakeTrainer.last["loss_fn"], nn.MSELoss)


def test_train_classification_optimizer_factory(tmp_path, monkeypatch):
    monkeypatch.setattr("mindtrace.models.training.Trainer", _FakeTrainer)
    sentinel = object()
    runner = _runner_for_train(tmp_path, optimizer_factory=lambda m, lr: sentinel)
    runner._train_classification(epochs=1, lr=0.1)
    assert _FakeTrainer.last["optimizer"] is sentinel
    assert isinstance(_FakeTrainer.last["loss_fn"], nn.CrossEntropyLoss)


def test_qat_detection_rejected(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[QAT()]),
        train_loader=_det_loader(),
        task="detection",
        num_classes=2,
        work_dir=tmp_path,
    )
    with pytest.raises(ValueError, match="QAT is not wired for detection"):
        runner._qat_step(QAT())


def test_quantize_dynamic_ignores_static_fields(tmp_path):
    """per_channel=False differs from the static-PTQ default, hitting the warning (649)."""
    recipe = OptimizationRecipe(
        steps=[Export(static_shape=(1, D)), Quantize(mode="dynamic", per_channel=False)]
    )
    result = OptimizationRunner(_linear_model(), recipe, work_dir=tmp_path).run()
    assert result.artifact_path.exists()


def test_static_quantize_requires_calibration(tmp_path):
    runner = OptimizationRunner(
        _linear_model(), OptimizationRecipe(steps=[Export()]), work_dir=tmp_path
    )
    dummy = tmp_path / "in.onnx"
    dummy.write_bytes(b"x")
    with pytest.raises(ValueError, match="requires a calibration_loader"):
        runner._quantize_step(Quantize(mode="static_ptq"), 0, dummy)


def test_static_quantize_classification(tmp_path, monkeypatch):
    captured = {}

    class _FakeSQ:
        def __init__(self, *, precision, per_channel, calibration_method):
            captured["precision"] = precision
            captured["per_channel"] = per_channel

        def run(self, onnx_path, calibration, *, samples, output):
            captured["calibration"] = calibration
            captured["samples"] = samples
            output.write_bytes(b"q")
            return output

    monkeypatch.setattr("mindtrace.models.optimization.quantize.StaticQuantizer", _FakeSQ)
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),
        calibration_loader=_loader(),
        work_dir=tmp_path,
    )
    art = tmp_path / "in.onnx"
    art.write_bytes(b"x")
    out = runner._quantize_step(Quantize(mode="static_ptq", precision="uint8"), 3, art)
    assert out.exists()
    assert captured["precision"] == "uint8"
    # A non-detection task feeds the raw calibration loader straight through.
    assert captured["calibration"] is runner.calibration_loader


def test_static_quantize_detection_flattens_feeds(tmp_path, monkeypatch):
    captured = {}

    class _FakeSQ:
        def __init__(self, **kwargs):
            pass

        def run(self, onnx_path, calibration, *, samples, output):
            captured["calibration"] = calibration
            output.write_bytes(b"q")
            return output

    monkeypatch.setattr("mindtrace.models.optimization.quantize.StaticQuantizer", _FakeSQ)
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),
        calibration_loader=_det_loader(),
        task="detection",
        num_classes=2,
        work_dir=tmp_path,
    )
    art = tmp_path / "in.onnx"
    art.write_bytes(b"x")
    out = runner._quantize_step(Quantize(mode="static_ptq", samples=2), 3, art)
    assert out.exists()
    # Detection loaders are flattened into a list of per-image [1, C, H, W] feeds.
    assert isinstance(captured["calibration"], list)
    assert captured["calibration"][0].shape == (1, 3, 8, 8)


def test_detection_calibration_feeds(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),
        calibration_loader=_det_loader(),
        task="detection",
        num_classes=2,
        work_dir=tmp_path,
    )
    # samples cap reached mid-batch -> early return (686-687)
    feeds = runner._detection_calibration_feeds(samples=1)
    assert len(feeds) == 1
    assert feeds[0].shape == (1, 3, 8, 8)
    # samples exceeds available -> full-loop return (688)
    feeds_all = runner._detection_calibration_feeds(samples=99)
    assert len(feeds_all) == 2


# ---------------------------------------------------------------------------
# Measurement / shape helpers (753, 759, 784, 789-794, 815)
# ---------------------------------------------------------------------------


def test_resolve_num_classes_detection_raises(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),
        eval_loader=_det_loader(),
        task="detection",
        work_dir=tmp_path,
    )
    with pytest.raises(ValueError, match="num_classes must be provided explicitly for detection"):
        runner._resolve_num_classes()


def test_resolve_num_classes_without_eval_loader_raises(tmp_path):
    runner = OptimizationRunner(
        _linear_model(), OptimizationRecipe(steps=[Export()]), work_dir=tmp_path
    )
    with pytest.raises(ValueError, match="num_classes could not be inferred"):
        runner._resolve_num_classes()


def test_infer_input_shape_detection_list(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),
        eval_loader=_det_loader(),
        task="detection",
        num_classes=2,
        work_dir=tmp_path,
    )
    assert runner._infer_input_shape() == (1, 3, 8, 8)


def test_infer_input_shape_from_static_shape_step(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export(static_shape=(1, D))]),
        work_dir=tmp_path,
    )
    assert runner._infer_input_shape() == (1, D)


def test_infer_input_shape_unresolvable_raises(tmp_path):
    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),  # no static_shape, no loaders
        work_dir=tmp_path,
    )
    with pytest.raises(ValueError, match="Could not infer the model input shape"):
        runner._infer_input_shape()


def test_first_batch_bare_tensor():
    inputs, targets = OptimizationRunner._first_batch([torch.randn(2, D)])
    assert inputs.shape == (2, D)
    assert targets is None


# ---------------------------------------------------------------------------
# _final_gates openvino branch (848-849) via mocked Benchmark
# ---------------------------------------------------------------------------


def test_final_gates_openvino_runtime(tmp_path, monkeypatch):
    class _FakeReport:
        runtime = "openvino"
        p95_ms = 1.0
        size_mb = 0.25

    class _FakeBench:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            return _FakeReport()

    monkeypatch.setattr(runner_module, "Benchmark", _FakeBench)

    runner = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export()]),
        constraints={"p95_latency_ms": 10.0, "max_size_mb": 10.0},
        work_dir=tmp_path,
    )
    runner._input_shape = (1, D)
    xml = tmp_path / "model.xml"
    xml.write_bytes(b"z")
    violations: list = []
    report = runner._final_gates("onnx", xml, violations)
    assert isinstance(report, _FakeReport)
    assert runner._final_gates.__name__  # sanity
    assert report.runtime == "openvino"
    assert violations == []
    assert runner._compiled_runtime is None


# ---------------------------------------------------------------------------
# Tracker logging (892-900)
# ---------------------------------------------------------------------------


class _RecordingTracker:
    def __init__(self):
        self.calls = []

    def log(self, metrics, step=None):
        self.calls.append((metrics, step))


def test_tracker_logs_metrics(tmp_path, monkeypatch):
    metrics = iter([0.9, 0.85])
    monkeypatch.setattr(
        runner_module.OptimizationRunner, "_measure_metric", lambda self, model_like: next(metrics)
    )
    tracker = _RecordingTracker()
    OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Prune(method="magnitude", sparsity=0.2)]),
        eval_loader=_loader(),
        constraints={"max_accuracy_drop": 1.0},
        tracker=tracker,
        work_dir=tmp_path,
    ).run()
    assert tracker.calls
    logged = tracker.calls[0][0]
    assert any("metric" in k for k in logged)
    assert any("metric_drop" in k for k in logged)


def test_tracker_log_failure_is_swallowed(tmp_path):
    class _BadTracker:
        def log(self, metrics, step=None):
            raise RuntimeError("tracker down")

    result = OptimizationRunner(
        _linear_model(),
        OptimizationRecipe(steps=[Export(static_shape=(1, D))]),
        tracker=_BadTracker(),
        work_dir=tmp_path,
    ).run()
    # Run completes despite the tracker raising.
    assert result.artifact_path.exists()
