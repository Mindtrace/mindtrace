"""Unit tests for mindtrace.models.optimization.recipes and .runner.

Covers:
- OptimizationRecipe: JSON round-trip preserves step order/types, unknown op
  rejected, save/load file round-trip
- OptimizationRunner: export-only recipe, full prune -> finetune -> export ->
  quantize pipeline (final artifact runs under ONNX Runtime), implicit export
  before a bare quantize step
- Accuracy gates: rollback records a violation and completes; on_violation
  "raise" raises OptimizationConstraintError
- Final gates: an impossible max_size_mb records a violation and attaches a
  BenchmarkReport

All models are tiny synthetic CNNs on random data; everything runs on CPU.
"""

from __future__ import annotations

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

import onnxruntime as ort  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402

from mindtrace.models.optimization import (  # noqa: E402
    Compile,
    Export,
    Finetune,
    OptimizationConstraintError,
    OptimizationRecipe,
    OptimizationRunner,
    Prune,
    Quantize,
)
from mindtrace.models.optimization import runner as runner_module  # noqa: E402

NUM_CLASSES = 4
INPUT_SHAPE = (3, 8, 8)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_cnn() -> nn.Module:
    """Tiny CNN: two convs, global pooling, linear head."""
    return nn.Sequential(
        nn.Conv2d(3, 8, 3, padding=1),
        nn.ReLU(),
        nn.Conv2d(8, 16, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(16, NUM_CLASSES),
    )


def _build_loader(n: int = 16, batch_size: int = 4) -> DataLoader:
    """Random tensor loader with (image, label) batches."""
    generator = torch.Generator().manual_seed(0)
    images = torch.randn(n, *INPUT_SHAPE, generator=generator)
    labels = torch.randint(0, NUM_CLASSES, (n,), generator=generator)
    return DataLoader(TensorDataset(images, labels), batch_size=batch_size)


def _ort_logits(path, batch_size: int = 2):
    """Run a random batch through an ONNX artifact and return the output."""
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    x = torch.randn(batch_size, *INPUT_SHAPE).numpy()
    return session.run(None, {session.get_inputs()[0].name: x})[0]


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------


class TestOptimizationRecipe:
    def test_json_round_trip_preserves_order_and_types(self, tmp_path):
        recipe = OptimizationRecipe(
            name="edge-int8",
            steps=[
                Prune(method="magnitude", sparsity=0.3, ignore=["head"]),
                Finetune(epochs=2, lr=5e-5),
                Export(opset=18, static_shape=(1, 3, 8, 8), simplify=False),
                Quantize(mode="dynamic", precision="uint8", samples=64, per_channel=False),
                Compile(target="ort-cpu"),
            ],
        )

        clone = OptimizationRecipe.from_json(recipe.to_json())
        assert clone == recipe
        assert [type(s) for s in clone.steps] == [Prune, Finetune, Export, Quantize, Compile]
        assert clone.steps[2].static_shape == (1, 3, 8, 8)

        path = recipe.save(tmp_path / "recipe.json")
        assert OptimizationRecipe.load(path) == recipe

    def test_unknown_op_rejected(self):
        bad = '{"name": "", "steps": [{"op": "distill"}]}'
        with pytest.raises(ValidationError):
            OptimizationRecipe.from_json(bad)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestOptimizationRunner:
    def test_export_only(self, tmp_path):
        result = OptimizationRunner(
            _build_cnn(),
            OptimizationRecipe(steps=[Export()]),
            eval_loader=_build_loader(),
            work_dir=tmp_path,
        ).run()

        assert result.artifact_path.exists()
        assert result.artifact_path.suffix == ".onnx"
        assert len(result.history) == 1
        assert result.history[0]["op"] == "export"
        assert result.history[0]["domain"] == "onnx"
        assert result.violations == []
        assert _ort_logits(result.artifact_path).shape == (2, NUM_CLASSES)

    def test_full_pipeline_prune_finetune_export_quantize(self, tmp_path):
        recipe = OptimizationRecipe(
            steps=[
                Prune(method="structured_channel", sparsity=0.3),
                Finetune(epochs=1, lr=1e-3),
                Export(),
                Quantize(mode="dynamic"),
            ]
        )
        result = OptimizationRunner(
            _build_cnn(),
            recipe,
            train_loader=_build_loader(),
            eval_loader=_build_loader(),
            work_dir=tmp_path,
        ).run()

        assert len(result.history) == 4
        assert [h["op"] for h in result.history] == ["prune", "finetune", "export", "quantize"]
        assert not any(h["rolled_back"] for h in result.history)
        assert result.artifact_path.exists()
        assert "quantize" in result.artifact_path.name
        assert _ort_logits(result.artifact_path).shape == (2, NUM_CLASSES)

    def test_implicit_export_before_bare_quantize(self, tmp_path):
        result = OptimizationRunner(
            _build_cnn(),
            OptimizationRecipe(steps=[Quantize(mode="dynamic")]),
            eval_loader=_build_loader(),
            work_dir=tmp_path,
        ).run()

        assert len(result.history) == 1
        assert result.history[0]["op"] == "quantize"
        assert result.history[0].get("implicit_export") is True
        assert result.artifact_path.exists()
        assert _ort_logits(result.artifact_path).shape == (2, NUM_CLASSES)

    def test_accuracy_gate_rollback(self, tmp_path, monkeypatch):
        # Baseline measures 0.9; the post-quantize measurement collapses to
        # 0.4, forcing a violation of max_accuracy_drop=0.05.
        metrics = iter([0.9, 0.4])
        monkeypatch.setattr(runner_module.OptimizationRunner, "_measure_metric", lambda self, model_like: next(metrics))

        result = OptimizationRunner(
            _build_cnn(),
            OptimizationRecipe(steps=[Export(), Quantize(mode="dynamic")]),
            eval_loader=_build_loader(),
            constraints={"max_accuracy_drop": 0.05},
            on_violation="rollback",
            work_dir=tmp_path,
        ).run()

        assert len(result.history) == 2
        quantize_entry = result.history[1]
        assert quantize_entry["rolled_back"] is True
        assert quantize_entry["metric_drop"] == pytest.approx(0.5)
        assert len(result.violations) == 1
        assert result.violations[0]["step"] == 1
        assert result.violations[0]["metric_drop"] == pytest.approx(0.5)
        # The run completed on the pre-quantize (exported) artifact.
        assert result.artifact_path.exists()
        assert "quantize" not in result.artifact_path.name

    def test_accuracy_gate_raise(self, tmp_path, monkeypatch):
        metrics = iter([0.9, 0.4])
        monkeypatch.setattr(runner_module.OptimizationRunner, "_measure_metric", lambda self, model_like: next(metrics))

        runner = OptimizationRunner(
            _build_cnn(),
            OptimizationRecipe(steps=[Export(), Quantize(mode="dynamic")]),
            eval_loader=_build_loader(),
            constraints={"max_accuracy_drop": 0.05},
            on_violation="raise",
            work_dir=tmp_path,
        )
        with pytest.raises(OptimizationConstraintError):
            runner.run()

    def test_final_size_gate_violation(self, tmp_path):
        result = OptimizationRunner(
            _build_cnn(),
            OptimizationRecipe(steps=[Export()]),
            eval_loader=_build_loader(),
            constraints={"max_size_mb": 0.000001},
            work_dir=tmp_path,
        ).run()

        assert result.report is not None
        assert result.report.runtime == "onnxruntime"
        size_violations = [v for v in result.violations if v.get("constraint") == "max_size_mb"]
        assert len(size_violations) == 1
        assert size_violations[0]["step"] == "final"
        assert size_violations[0]["value"] > size_violations[0]["limit"]


class TestRunnerRegressions:
    """Regression tests for confirmed review findings."""

    def test_unknown_constraint_key_rejected(self):
        with pytest.raises(ValueError, match="Unknown constraint keys"):
            OptimizationRunner(
                _build_cnn(),
                OptimizationRecipe(steps=[Export()]),
                eval_loader=_build_loader(),
                constraints={"p95_latencyms": 10},
            )

    def test_accuracy_gate_without_eval_loader_rejected(self):
        with pytest.raises(ValueError, match="max_accuracy_drop"):
            OptimizationRunner(
                _build_cnn(),
                OptimizationRecipe(steps=[Export()]),
                constraints={"max_accuracy_drop": 0.02},
            )

    def test_loaderless_run_uses_export_static_shape(self, tmp_path):
        """Export(static_shape=...) must satisfy final gates with no loader at all."""
        recipe = OptimizationRecipe(steps=[Export(static_shape=(1, *INPUT_SHAPE))])
        result = OptimizationRunner(
            _build_cnn(),
            recipe,
            constraints={"max_size_mb": 500},
            work_dir=tmp_path,
        ).run()
        assert result.artifact_path.exists()
        assert result.report is not None
        assert result.violations == []

    def test_unbenchmarkable_runtime_skips_latency_gate(self, tmp_path, monkeypatch):
        """A recipe ending in a TensorRT-style compile must complete and size-gate."""
        from mindtrace.models.optimization.compile.base import _COMPILERS, CompiledArtifact

        def _fake_trt(onnx_path, target, output_dir, **opts):
            plan = output_dir / "model.plan"
            plan.write_bytes(b"\x00" * 2048)
            return CompiledArtifact(path=plan, target=target.name, runtime="tensorrt", meta={})

        monkeypatch.setitem(_COMPILERS, "tensorrt", _fake_trt)

        recipe = OptimizationRecipe(steps=[Export(static_shape=(1, *INPUT_SHAPE)), Compile(target="jetson-orin-nx")])
        result = OptimizationRunner(
            _build_cnn(),
            recipe,
            eval_loader=_build_loader(),
            constraints={"p95_latency_ms": 20, "max_size_mb": 100},
            work_dir=tmp_path,
        ).run()
        assert result.artifact_path.suffix == ".plan"
        assert result.report is None  # latency benchmark skipped, run not lost
        assert all(v.get("constraint") != "p95_latency_ms" for v in result.violations)
        # size gate still enforced from the file itself (2KB < 100MB -> no violation)
        assert all(v.get("constraint") != "max_size_mb" for v in result.violations)

    def test_dynamic_quantize_honors_precision(self, tmp_path):
        recipe = OptimizationRecipe(
            steps=[Export(static_shape=(1, *INPUT_SHAPE)), Quantize(mode="dynamic", precision="uint8")]
        )
        result = OptimizationRunner(_build_cnn(), recipe, work_dir=tmp_path).run()
        assert result.artifact_path.exists()
        _ort_logits(result.artifact_path)

    def test_unmocked_gate_measurement_matches_torch(self, tmp_path):
        """OnnxModelAdapter + EvaluationRunner must reproduce the torch metric."""
        model = _build_cnn().eval()
        loader = _build_loader(n=32)
        runner = OptimizationRunner(
            model,
            OptimizationRecipe(steps=[Export(static_shape=(1, *INPUT_SHAPE))]),
            eval_loader=loader,
            work_dir=tmp_path,
        )
        result = runner.run()
        torch_metric = runner._measure_metric(model)
        onnx_metric = runner._measure_metric(runner_module.OnnxModelAdapter(result.artifact_path))
        assert onnx_metric == pytest.approx(torch_metric, abs=1e-6)
