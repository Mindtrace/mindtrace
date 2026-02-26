"""10_automation_pipeline.py — TrainingPipeline and InferencePipeline.

Demonstrates the mindtrace.automation pipeline layer that composes
mindtrace-models artefacts into reproducible, observable workflows.

  SECTION 1 — TrainingPipeline
      train → evaluate → conditionally promote to staging registry

  SECTION 2 — InferencePipeline (dry_run mode)
      fetch_records → run_inference → (skip store — dry_run=True)

  SECTION 3 — InferencePipeline (live store)
      fetch_records → run_inference → store_results

  SECTION 4 — PipelineResult inspection
      success flag, per-step metadata, failed_steps()

  SECTION 5 — Custom PipelineStep composition
      Show how to extend Pipeline with your own steps

The pipelines use lightweight duck-typed mocks so the script runs without
external infrastructure (no real datalake, no GPU needed).

Run:
    python samples/models/10_automation_pipeline.py
"""

import asyncio
import tempfile
from dataclasses import dataclass, field
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.registry import Registry
from mindtrace.models import (
    build_model,
    build_optimizer,
    ModelCard,
    ModelStage,
    promote,
)
from mindtrace.automation.pipeline import (
    InferenceConfig,
    InferencePipeline,
    Pipeline,
    PipelineStatus,
    PipelineStep,
    StepResult,
    TrainingConfig,
    TrainingPipeline,
)


# ── Mock collaborators ─────────────────────────────────────────────────────────

class _MockTrainer:
    """Duck-typed trainer — only .train(**kwargs) required."""

    def __init__(self, model: nn.Module):
        self._model = model

    def train(self, **kwargs) -> dict:
        # Simulate one epoch of training and return metrics.
        x = torch.randn(32, 3, 32, 32)
        y = torch.randint(0, 4, (32,))
        logits = self._model(x)
        loss   = nn.CrossEntropyLoss()(logits, y)
        acc    = (logits.argmax(1) == y).float().mean().item()
        print(f"  [MockTrainer] loss={loss.item():.4f}  accuracy={acc:.4f}")
        return {"loss": loss.item(), "accuracy": acc}


class _MockEvaluator:
    """Duck-typed evaluator — only .evaluate(**kwargs) required."""

    def __init__(self, accuracy: float = 0.82):
        self._accuracy = accuracy

    def evaluate(self, **kwargs) -> dict:
        print(f"  [MockEvaluator] accuracy={self._accuracy:.4f}")
        return {"accuracy": self._accuracy, "loss": 0.31}


class _MockDatalake:
    """Duck-typed datalake — async query_data / store_data."""

    def __init__(self, records: list[dict]):
        self._records = records
        self.stored: list[dict] = []

    async def query_data(self, query: dict, datums_wanted: int | None = None) -> list[dict]:
        results = [r for r in self._records if all(r.get(k) == v for k, v in query.items())]
        if datums_wanted:
            results = results[:datums_wanted]
        return results

    async def store_data(self, record: dict, schema: str | None = None) -> None:
        self.stored.append(record)


class _MockService:
    """Duck-typed model service — only .predict(input) required."""

    def predict(self, inp: Any) -> dict:
        return {"label": "weld_ok", "confidence": 0.93}


# ── Section 1 — TrainingPipeline ───────────────────────────────────────────────

def demo_training_pipeline():
    print("\n" + "=" * 60)
    print("SECTION 1 — TrainingPipeline: train → evaluate → promote")
    print("=" * 60)

    tmpdir  = tempfile.mkdtemp(prefix="mt_auto_train_")
    registry = Registry(tmpdir)

    model    = build_model("resnet18", head="linear", num_classes=4, pretrained=False)
    trainer  = _MockTrainer(model)
    evaluator = _MockEvaluator(accuracy=0.84)

    pipeline = TrainingPipeline.build(
        name="weld_classifier_training",
        trainer=trainer,
        evaluator=evaluator,
        registry=registry,
        config=TrainingConfig(
            model_name="weld_classifier",
            version="v1",
            promote_on_improvement=True,
            min_accuracy_gain=0.0,     # promote whenever eval > baseline
        ),
    )

    result = pipeline.run()

    print(f"\nPipeline: {result.pipeline_name}")
    print(f"Status  : {result.status.value}")
    print(f"Duration: {result.total_duration_s:.3f}s")
    print("\nStep summary:")
    for step in result.steps:
        print(f"  [{step.status.value:7s}] {step.step_name:<20s} {step.metadata}")

    return result


# ── Section 2 — InferencePipeline (dry_run) ────────────────────────────────────

def demo_inference_pipeline_dry_run():
    print("\n" + "=" * 60)
    print("SECTION 2 — InferencePipeline (dry_run=True)")
    print("=" * 60)

    records = [
        {"id": i, "type": "weld_image", "path": f"/data/img_{i:04d}.jpg"}
        for i in range(20)
    ]
    datalake = _MockDatalake(records)
    service  = _MockService()

    def transform(record: dict) -> dict:
        """Strip datalake metadata, keep only what the service needs."""
        return {"path": record["path"]}

    pipeline = InferencePipeline.build(
        name="weld_inference_dry",
        datalake=datalake,
        service=service,
        config=InferenceConfig(
            query={"type": "weld_image"},
            datums_wanted=10,
            batch_size=5,
            transform=transform,
            dry_run=True,       # ← no writes to datalake
        ),
    )

    result = pipeline.run()
    print(f"\nStatus : {result.status.value}")
    print(f"Steps  : {[s.step_name for s in result.steps]}")

    infer_step = next(s for s in result.steps if s.step_name == "run_inference")
    print(f"Inference metadata: {infer_step.metadata}")

    # Dry-run → nothing stored
    print(f"Records stored in datalake: {len(datalake.stored)}  (expected 0)")


# ── Section 3 — InferencePipeline (live store) ────────────────────────────────

def demo_inference_pipeline_live():
    print("\n" + "=" * 60)
    print("SECTION 3 — InferencePipeline (live store)")
    print("=" * 60)

    records = [
        {"id": i, "type": "weld_image", "path": f"/data/img_{i:04d}.jpg"}
        for i in range(8)
    ]
    datalake = _MockDatalake(records)
    service  = _MockService()

    pipeline = InferencePipeline.build(
        name="weld_inference_live",
        datalake=datalake,
        service=service,
        config=InferenceConfig(
            query={"type": "weld_image"},
            batch_size=4,
            result_schema="weld_predictions",
            dry_run=False,      # ← writes predictions back to datalake
        ),
    )

    result = pipeline.run()
    print(f"\nStatus  : {result.status.value}")
    store_step = next((s for s in result.steps if s.step_name == "store_results"), None)
    if store_step:
        print(f"Store metadata: {store_step.metadata}")
    print(f"Records now in datalake.stored: {len(datalake.stored)}")


# ── Section 4 — PipelineResult inspection ─────────────────────────────────────

def demo_result_inspection():
    print("\n" + "=" * 60)
    print("SECTION 4 — PipelineResult properties and failed_steps()")
    print("=" * 60)

    # Build a pipeline guaranteed to fail at a specific step.
    class _FailStep(PipelineStep):
        name = "always_fail"

        def run(self, context: dict) -> StepResult:
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.FAILED,
                error="Simulated failure for demo",
                metadata={"code": 500},
            )

    class _DemoFail(Pipeline):
        pass

    pipeline = _DemoFail(name="failure_demo")
    pipeline.add_step(_FailStep())

    result = pipeline.run()
    print(f"result.success      : {result.success}")
    print(f"result.status       : {result.status.value}")
    print(f"result.failed_steps : {[s.step_name for s in result.failed_steps()]}")
    print(f"Step error          : {result.steps[0].error}")


# ── Section 5 — Custom PipelineStep composition ────────────────────────────────

def demo_custom_steps():
    print("\n" + "=" * 60)
    print("SECTION 5 — Custom PipelineStep composition")
    print("=" * 60)

    class _ValidateDataStep(PipelineStep):
        """Check record count meets a minimum threshold."""

        name = "validate_data"

        def __init__(self, min_records: int) -> None:
            self._min = min_records

        def run(self, context: dict) -> StepResult:
            records = context.get("records", [])
            ok = len(records) >= self._min
            context["data_valid"] = ok
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS if ok else PipelineStatus.FAILED,
                metadata={"count": len(records), "min_required": self._min, "valid": ok},
                error=None if ok else f"Only {len(records)} records, need {self._min}",
            )

    class _AugmentRecordsStep(PipelineStep):
        """Add a 'split' field to each record based on index."""

        name = "augment_records"

        def run(self, context: dict) -> StepResult:
            records = context.get("records", [])
            for i, rec in enumerate(records):
                rec["split"] = "train" if i < len(records) * 0.8 else "val"
            context["records"] = records
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={"augmented": len(records)},
            )

    class _DataPipeline(Pipeline):
        pass

    records = [{"id": i, "value": i * 1.5} for i in range(10)]
    pipeline = _DataPipeline(name="custom_data_pipeline")
    pipeline.add_step(_ValidateDataStep(min_records=5))
    pipeline.add_step(_AugmentRecordsStep())

    result = pipeline.run(initial_context={"records": records})
    print(f"Status : {result.status.value}")
    for s in result.steps:
        print(f"  [{s.status.value:7s}] {s.step_name}: {s.metadata}")
    print(f"First record after augmentation: {records[0]}")
    print(f"Last record after augmentation : {records[-1]}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_training_pipeline()
    demo_inference_pipeline_dry_run()
    demo_inference_pipeline_live()
    demo_result_inspection()
    demo_custom_steps()
    print("\n✓ 10_automation_pipeline.py complete.")
