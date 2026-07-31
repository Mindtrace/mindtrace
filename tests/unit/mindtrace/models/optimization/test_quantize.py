"""Unit tests for mindtrace.models.optimization.quantize.

Covers:
- quantize_dynamic: default output suffix, file shrinks vs FP32
- StaticQuantizer: calibration via torch DataLoader and via a numpy iterable,
  quantized model runs under ONNX Runtime and is smaller than FP32
- QATCallback: end-to-end with the real Trainer, convert() produces a
  runnable INT8 model
- sensitivity_scan: sorted worst-first report with a deterministic fake eval
- MixedPrecisionSearch: greedy exclusion converges and meets the constraint

All models are tiny synthetic CNNs exported inline; everything runs on CPU.
"""

from __future__ import annotations

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Environment fixtures (must exist before any Mindtrace import)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


# ---------------------------------------------------------------------------
# Imports (after env fixture is declared so collection order is correct)
# ---------------------------------------------------------------------------

import onnx  # noqa: E402
import onnxruntime as ort  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402

from mindtrace.models.optimization.quantize import (  # noqa: E402
    MixedPrecisionSearch,
    QATCallback,
    QuantPlan,
    SensitivityReport,
    StaticQuantizer,
    quantize_dynamic,
    sensitivity_scan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_cnn() -> nn.Module:
    """CNN with enough weights that INT8 meaningfully shrinks the file."""
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1),
        nn.ReLU(),
        nn.Conv2d(16, 32, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(4),
        nn.Flatten(),
        nn.Linear(32 * 16, 128),
        nn.ReLU(),
        nn.Linear(128, 10),
    )


def _build_two_conv() -> nn.Module:
    """Two-conv model used for sensitivity / mixed-precision tests."""
    return nn.Sequential(
        nn.Conv2d(3, 4, 3, padding=1),
        nn.ReLU(),
        nn.Conv2d(4, 8, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(8, 2),
    )


def _export(model: nn.Module, path, input_shape=(1, 3, 32, 32)):
    model.eval()
    torch.onnx.export(
        model,
        (torch.randn(*input_shape),),
        str(path),
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )
    return path


def _run_ort(path, input_shape=(1, 3, 32, 32)):
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    feed = {"input": np.random.randn(*input_shape).astype(np.float32)}
    return session.run(None, feed)[0]


@pytest.fixture(scope="module")
def cnn_onnx(tmp_path_factory):
    torch.manual_seed(0)
    path = tmp_path_factory.mktemp("cnn") / "cnn.onnx"
    return _export(_build_cnn(), path)


@pytest.fixture(scope="module")
def two_conv_onnx(tmp_path_factory):
    torch.manual_seed(0)
    path = tmp_path_factory.mktemp("two_conv") / "two_conv.onnx"
    return _export(_build_two_conv(), path)


def _quantized_weight_prefixes(path) -> set[str]:
    """Names of original weight initializers that were quantized to INT8."""
    model = onnx.load(str(path))
    return {
        init.name.removesuffix("_quantized") for init in model.graph.initializer if init.name.endswith("_quantized")
    }


def _fake_eval(path) -> float:
    """Deterministic metric: penalise quantization of specific layers.

    conv1 (``0.weight``) costs 0.3, conv2 (``2.weight``) costs 0.1 and the
    final Gemm (``6.weight``) costs 0.05.  The FP32 model scores 1.0.
    """
    quantized = _quantized_weight_prefixes(path)
    score = 1.0
    if "0.weight" in quantized:
        score -= 0.3
    if "2.weight" in quantized:
        score -= 0.1
    if "6.weight" in quantized:
        score -= 0.05
    return score


# ---------------------------------------------------------------------------
# quantize_dynamic
# ---------------------------------------------------------------------------


class TestQuantizeDynamic:
    def test_shrinks_file_with_default_suffix(self, cnn_onnx):
        out = quantize_dynamic(cnn_onnx)

        assert out.name == "cnn-int8-dynamic.onnx"
        assert out.exists()
        assert out.stat().st_size < cnn_onnx.stat().st_size
        # The quantized model still runs and preserves the output shape.
        assert _run_ort(out).shape == (1, 10)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            quantize_dynamic(tmp_path / "nope.onnx")

    def test_preprocesses_before_quantizing(self, cnn_onnx, tmp_path, monkeypatch):
        """Dynamic quantization must pre-process the graph first (shape inference),
        matching the static path. Without it, models with a dimension-reducing head
        (e.g. a 768->9 classifier MatMul) fail at session load with
        "Inferred shape and existing shape differ". This locks the fix in place."""
        from mindtrace.models.optimization.quantize import ptq

        calls = []
        real = ptq.preprocess_for_quantization
        monkeypatch.setattr(ptq, "preprocess_for_quantization", lambda p, w: calls.append(p) or real(p, w))

        out = quantize_dynamic(cnn_onnx, tmp_path / "pre.onnx")

        assert calls, "quantize_dynamic did not pre-process the model before quantizing"
        assert _run_ort(out).shape == (1, 10)  # loads and runs after preprocessing


# ---------------------------------------------------------------------------
# StaticQuantizer
# ---------------------------------------------------------------------------


class TestStaticQuantizer:
    def test_with_dataloader(self, cnn_onnx, tmp_path):
        dataset = TensorDataset(torch.randn(16, 3, 32, 32), torch.randint(0, 10, (16,)))
        loader = DataLoader(dataset, batch_size=4)

        out = StaticQuantizer(per_channel=True, calibration_method="minmax").run(
            cnn_onnx, loader, samples=8, output=tmp_path / "static-dl.onnx"
        )

        assert out.exists()
        assert out.stat().st_size < cnn_onnx.stat().st_size
        assert _run_ort(out).shape == (1, 10)

    def test_with_numpy_iterable(self, cnn_onnx):
        arrays = [np.random.randn(1, 3, 32, 32).astype(np.float32) for _ in range(6)]

        out = StaticQuantizer().run(cnn_onnx, arrays, samples=6)

        assert out.name == "cnn-int8-static.onnx"
        assert out.stat().st_size < cnn_onnx.stat().st_size
        assert _run_ort(out).shape == (1, 10)

    def test_invalid_settings_raise(self):
        with pytest.raises(ValueError, match="precision"):
            StaticQuantizer(precision="int3")
        with pytest.raises(ValueError, match="calibration_method"):
            StaticQuantizer(calibration_method="magic")


# ---------------------------------------------------------------------------
# QATCallback
# ---------------------------------------------------------------------------


class TestQATCallback:
    def test_end_to_end_with_trainer(self):
        from mindtrace.models.training.trainer import Trainer

        torch.manual_seed(0)
        model = nn.Sequential(
            nn.Conv2d(3, 4, 3),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(4 * 6 * 6, 2),
        )
        dataset = TensorDataset(torch.randn(16, 3, 8, 8), torch.randint(0, 2, (16,)))
        loader = DataLoader(dataset, batch_size=4)

        qat = QATCallback(start_epoch=0, backend="x86")
        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=torch.optim.SGD(model.parameters(), lr=0.01),
            callbacks=[qat],
            device="cpu",
        )
        history = trainer.fit(loader, epochs=2)

        assert len(history["train/loss"]) == 2
        # The trainer's model was swapped for the fake-quantized copy.
        assert qat.prepared_model is not None
        assert trainer.model is qat.prepared_model
        assert trainer.model is not model
        # The optimizer now tracks the prepared model's parameters.
        prepared_params = {id(p) for p in trainer.model.parameters()}
        assert all(id(p) in prepared_params for p in trainer.optimizer.param_groups[0]["params"])

        int8_model = qat.convert()
        out = int8_model(torch.randn(2, 3, 8, 8))
        assert out.shape == (2, 2)
        # Conversion produced genuinely quantized submodules.
        module_types = {type(m).__module__ for m in int8_model.modules()}
        assert any("quantized" in mod for mod in module_types)

    def test_convert_before_training_raises(self):
        qat = QATCallback()
        with pytest.raises(RuntimeError, match="before QAT was activated"):
            qat.convert()


# ---------------------------------------------------------------------------
# sensitivity_scan
# ---------------------------------------------------------------------------


class TestSensitivityScan:
    def test_ranks_nodes_worst_first(self, two_conv_onnx):
        calib = [np.random.randn(1, 3, 32, 32).astype(np.float32) for _ in range(4)]

        report = sensitivity_scan(two_conv_onnx, _fake_eval, calib, samples=4)

        assert isinstance(report, SensitivityReport)
        assert report.baseline_metric == pytest.approx(1.0)
        assert report.full_quant_drop == pytest.approx(0.45)
        assert len(report.node_drops) == 3

        ranked = report.top()
        drops = [drop for _, drop in ranked]
        assert drops == sorted(drops, reverse=True)
        assert drops[0] == pytest.approx(0.3)  # conv1 is the most sensitive
        assert "Conv" in ranked[0][0]
        assert report.top(1) == ranked[:1]

        as_dict = report.to_dict()
        assert set(as_dict) == {"baseline_metric", "full_quant_drop", "node_drops"}
        assert as_dict["node_drops"] == report.node_drops


# ---------------------------------------------------------------------------
# MixedPrecisionSearch
# ---------------------------------------------------------------------------


class TestMixedPrecisionSearch:
    def test_converges_to_constraint(self, two_conv_onnx, tmp_path):
        calib = [np.random.randn(1, 3, 32, 32).astype(np.float32) for _ in range(4)]

        search = MixedPrecisionSearch({"max_accuracy_drop": 0.2}, calib)
        plan = search.run(two_conv_onnx, _fake_eval, samples=4, output=tmp_path / "mixed.onnx")

        assert isinstance(plan, QuantPlan)
        # Excluding only the most sensitive conv (drop 0.3) leaves 0.15 <= 0.2.
        assert len(plan.nodes_to_exclude) == 1
        assert "Conv" in plan.nodes_to_exclude[0]
        assert plan.achieved_drop == pytest.approx(0.15)
        assert plan.achieved_drop <= 0.2
        assert plan.quantized_path.exists()
        assert _run_ort(plan.quantized_path).shape == (1, 2)

    def test_no_exclusions_when_constraint_already_met(self, two_conv_onnx, tmp_path):
        calib = [np.random.randn(1, 3, 32, 32).astype(np.float32) for _ in range(4)]

        search = MixedPrecisionSearch({"max_accuracy_drop": 1.0}, calib)
        plan = search.run(two_conv_onnx, _fake_eval, samples=4, output=tmp_path / "full.onnx")

        assert plan.nodes_to_exclude == []
        assert plan.achieved_drop == pytest.approx(0.45)

    def test_missing_constraint_raises(self):
        with pytest.raises(ValueError, match="max_accuracy_drop"):
            MixedPrecisionSearch({}, [])


class TestCalibrationLayouts:
    """Regression tests for calibration batch handling across input layouts."""

    def test_bare_tensor_batches_split_for_batch1_model(self, cnn_onnx, tmp_path):
        """Unlabeled DataLoader batches (bare tensors) must calibrate a batch-1 model."""
        loader = DataLoader(TensorDataset(torch.randn(8, 3, 32, 32)), batch_size=4)
        bare_loader = (batch[0] for batch in loader)  # yields bare (4, 3, 32, 32) tensors
        out = StaticQuantizer().run(cnn_onnx, bare_loader, samples=8, output=tmp_path / "bare.onnx")
        assert out.exists()
        _run_ort(out)

    def test_samples_budget_counts_samples_not_batches(self, cnn_onnx):
        """samples=N must cap the number of individual samples for bare-tensor input."""
        from mindtrace.models.optimization.quantize.ptq import _resolve_input_info, collect_feeds

        name, rank, batch = _resolve_input_info(cnn_onnx)
        batches = [torch.randn(4, 3, 32, 32) for _ in range(4)]  # 16 samples total
        feeds = collect_feeds(batches, name, 6, sample_rank=rank - 1, batch_size=batch)
        assert len(feeds) == 6
        assert all(feed[name].shape[0] == 1 for feed in feeds)

    def test_single_sample_3d_gains_batch_dim(self, cnn_onnx):
        """A dataset yielding (3, 32, 32) samples must not be split along channels."""
        from mindtrace.models.optimization.quantize.ptq import _resolve_input_info, collect_feeds

        name, rank, _ = _resolve_input_info(cnn_onnx)
        samples_3d = [(torch.randn(3, 32, 32), 0) for _ in range(3)]
        feeds = collect_feeds(samples_3d, name, 10, sample_rank=rank - 1)
        assert len(feeds) == 3
        assert all(feed[name].shape == (1, 3, 32, 32) for feed in feeds)

    def test_fixed_batch4_model_gets_grouped_feeds(self, tmp_path):
        """Models exported with a fixed batch of 4 calibrate with feeds of exactly 4."""
        model_path = _export(_build_two_conv(), tmp_path / "b4.onnx", input_shape=(4, 3, 16, 16))
        loader = DataLoader(TensorDataset(torch.randn(10, 3, 16, 16), torch.zeros(10)), batch_size=3)
        out = StaticQuantizer().run(model_path, loader, samples=10, output=tmp_path / "b4-int8.onnx")
        assert out.exists()
        _run_ort(out, input_shape=(4, 3, 16, 16))

    def test_dict_feed_preserves_dtype(self):
        """Dict calibration batches must keep the caller's dtypes (e.g. int64 ids)."""
        from mindtrace.models.optimization.quantize.ptq import _batch_to_arrays

        feed = _batch_to_arrays({"ids": np.arange(4, dtype=np.int64), "x": torch.randn(1, 3)}, "input")[0]
        assert feed["ids"].dtype == np.int64
        assert feed["x"].dtype == np.float32


class TestQuantizeDynamicPrecision:
    """Regression tests for the precision parameter on dynamic quantization."""

    def test_uint8_precision(self, cnn_onnx, tmp_path):
        out = quantize_dynamic(cnn_onnx, tmp_path / "u8.onnx", precision="uint8")
        assert out.exists()
        _run_ort(out)

    def test_invalid_precision_raises(self, cnn_onnx):
        with pytest.raises(ValueError, match="precision"):
            quantize_dynamic(cnn_onnx, precision="int4")


class TestQATOptimizerGroups:
    """Regression test: QAT preparation must preserve param-group structure."""

    def test_differential_lr_groups_survive_preparation(self):
        model = nn.Sequential(nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 2))
        backbone_params = list(model[0].parameters())
        head_params = list(model[2].parameters())
        optimizer = torch.optim.AdamW([{"params": backbone_params, "lr": 1e-5}, {"params": head_params, "lr": 1e-3}])

        from mindtrace.models.training.trainer import Trainer

        trainer = Trainer(model=model, loss_fn=nn.CrossEntropyLoss(), optimizer=optimizer, device="cpu")
        callback = QATCallback(example_inputs=(torch.randn(2, 8),))
        callback.on_train_begin(trainer)
        callback._current_epoch = 0
        callback.on_epoch_begin(trainer, epoch=0)

        groups = trainer.optimizer.param_groups
        assert len(groups) == 2
        assert groups[0]["lr"] == pytest.approx(1e-5)
        assert groups[1]["lr"] == pytest.approx(1e-3)
        prepared_names = dict(trainer.model.named_parameters())
        assert sum(len(g["params"]) for g in groups) == sum(1 for p in prepared_names.values() if p.requires_grad)
