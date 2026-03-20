"""Tests for TrainingPipeline with real mindtrace.models components.

Verifies that the automation pipeline layer correctly orchestrates
Trainer.train() and EvaluationRunner.evaluate() without adapters.
"""

from __future__ import annotations

import tempfile

import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.automation.pipeline import (
    TrainingConfig,
    TrainingPipeline,
)
from mindtrace.models import (
    EvaluationRunner,
    Trainer,
    build_model,
    build_optimizer,
)
from mindtrace.registry import Registry

# -- Fixtures ----------------------------------------------------------------

NUM_CLASSES = 3
BATCH_SIZE = 8


@pytest.fixture()
def synthetic_loaders():
    """Create small synthetic train / val DataLoaders."""
    train_x = torch.randn(32, 3, 32, 32)
    train_y = torch.randint(0, NUM_CLASSES, (32,))
    val_x = torch.randn(16, 3, 32, 32)
    val_y = torch.randint(0, NUM_CLASSES, (16,))
    train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE)
    val_loader = DataLoader(TensorDataset(val_x, val_y), batch_size=BATCH_SIZE)
    return train_loader, val_loader


@pytest.fixture()
def model():
    return build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)


@pytest.fixture()
def trainer(model, synthetic_loaders):
    train_loader, val_loader = synthetic_loaders
    optimizer = build_optimizer("adamw", model, lr=1e-3)
    return Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=optimizer,
        train_loader=train_loader,
        val_loader=val_loader,
    )


@pytest.fixture()
def evaluator(model, synthetic_loaders):
    _, val_loader = synthetic_loaders
    return EvaluationRunner(
        model=model,
        task="classification",
        num_classes=NUM_CLASSES,
        loader=val_loader,
    )


@pytest.fixture()
def registry():
    with tempfile.TemporaryDirectory(prefix="mt_test_") as tmpdir:
        yield Registry(tmpdir)


# -- Trainer.train() ---------------------------------------------------------


class TestTrainerTrainMethod:
    """Trainer.train() is the interface TrainingPipeline._TrainStep expects."""

    def test_train_returns_flat_metrics(self, trainer):
        metrics = trainer.train(epochs=1)
        assert isinstance(metrics, dict)
        assert "train/loss" in metrics
        assert "val/loss" in metrics
        assert isinstance(metrics["train/loss"], float)

    def test_train_uses_stored_loaders(self, trainer):
        """Should work without passing loaders explicitly."""
        metrics = trainer.train(epochs=1)
        assert metrics  # non-empty

    def test_train_raises_without_loader(self, model):
        optimizer = build_optimizer("adamw", model, lr=1e-3)
        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=optimizer,
        )
        with pytest.raises(ValueError, match="train_loader is required"):
            trainer.train()


# -- EvaluationRunner.evaluate() ---------------------------------------------


class TestEvaluationRunnerEvaluateMethod:
    """EvaluationRunner.evaluate() is the interface _EvalStep expects."""

    def test_evaluate_returns_metrics(self, evaluator):
        results = evaluator.evaluate()
        assert "accuracy" in results
        assert "precision" in results
        assert isinstance(results["accuracy"], float)

    def test_evaluate_uses_stored_loader(self, evaluator):
        results = evaluator.evaluate()
        assert results  # non-empty

    def test_evaluate_raises_without_loader(self, model):
        runner = EvaluationRunner(
            model=model,
            task="classification",
            num_classes=NUM_CLASSES,
        )
        with pytest.raises(ValueError, match="loader is required"):
            runner.evaluate()


# -- TrainingPipeline end-to-end ---------------------------------------------


class TestTrainingPipeline:
    """TrainingPipeline wires real Trainer + EvaluationRunner."""

    def test_train_eval_pipeline(self, trainer, evaluator):
        pipeline = TrainingPipeline.build(
            name="test_train_eval",
            trainer=trainer,
            evaluator=evaluator,
            config=TrainingConfig(
                model_name="test_model",
                version="v1",
                trainer_kwargs={"epochs": 1},
            ),
        )
        result = pipeline.run()
        assert result.success
        assert len(result.steps) == 2
        assert result.steps[0].step_name == "train"
        assert result.steps[1].step_name == "evaluate"

    def test_train_only_pipeline(self, trainer):
        pipeline = TrainingPipeline.build(
            name="test_train_only",
            trainer=trainer,
            config=TrainingConfig(
                model_name="test_model",
                version="v1",
                trainer_kwargs={"epochs": 1},
            ),
        )
        result = pipeline.run()
        assert result.success
        assert len(result.steps) == 1
        assert result.steps[0].step_name == "train"

    def test_train_eval_promote_pipeline(self, trainer, evaluator, registry):
        pipeline = TrainingPipeline.build(
            name="test_full_pipeline",
            trainer=trainer,
            evaluator=evaluator,
            registry=registry,
            config=TrainingConfig(
                model_name="test_model",
                version="v1",
                promote_on_improvement=True,
                min_accuracy_gain=0.0,
                trainer_kwargs={"epochs": 1},
            ),
        )
        result = pipeline.run()
        assert result.success
        assert len(result.steps) == 3
        assert result.steps[2].step_name == "promote"
