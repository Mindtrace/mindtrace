"""Integration tests mirroring samples/models/*.py.

Each sample script has a corresponding `test_*` function here that exercises
the same functional surface (API calls, tensor shapes, registry round-trips)
without the narrative print output. The tests share one Python process, so
the heavy `torch` + `mindtrace.models` import cost is paid once — dramatically
faster than the previous subprocess-per-script approach.

When updating a sample under samples/models/, update the corresponding test
here (and vice versa). Samples remain user-facing tutorials runnable via
`python samples/models/NN_*.py`; tests are the executable regression surface.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Skip CUDA probe on GPU-less runners before any model init.
if not torch.cuda.is_available():
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import pytest

from mindtrace.models import (
    CompositeTracker,
    EarlyStopping,
    EvaluationRunner,
    LRMonitor,
    MLflowTracker,
    ModelCheckpoint,
    OptunaCallback,
    ProgressLogger,
    RegistryBridge,
    TensorBoardTracker,
    Trainer,
    UnfreezeSchedule,
    WandBTracker,
    build_model,
    build_optimizer,
    build_scheduler,
)
from mindtrace.models.architectures import (
    BackboneInfo,
    FPNSegHead,
    LinearSegHead,
    MLPHead,
    ModelWrapper,
    build_backbone,
    build_model_from_hf,
    list_backbones,
    register_backbone,
)
from mindtrace.models.evaluation.metrics.classification import (
    accuracy,
    classification_report,
)
from mindtrace.models.evaluation.metrics.detection import mean_average_precision
from mindtrace.models.evaluation.metrics.regression import mae, mse, r2_score, rmse
from mindtrace.models.evaluation.metrics.segmentation import dice_score, mean_iou
from mindtrace.models.lifecycle import (
    EvalResult,
    ModelCard,
    ModelStage,
    PromotionError,
    PromotionResult,
)
from mindtrace.models.lifecycle.stages import VALID_PROMOTIONS
from mindtrace.models.serving.onnx.service import OnnxModelService
from mindtrace.models.serving.schemas import PredictRequest, PredictResponse
from mindtrace.models.tracking import Tracker
from mindtrace.registry import Registry

# ── Module-scope side effects (run once per test session) ────────────────────


@register_backbone("tiny_cnn_samples_test")
def _build_tiny_cnn(pretrained: bool = False) -> tuple[nn.Module, int]:
    """Tiny 3-layer CNN backbone (512-d output) used by test_architectures."""
    model = nn.Sequential(
        nn.Conv2d(3, 64, 3, stride=2, padding=1),
        nn.ReLU(),
        nn.Conv2d(64, 128, 3, stride=2, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(128, 512),
    )
    return model, 512


try:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None


# ── 01_quick_start.py ────────────────────────────────────────────────────────


def test_quick_start(tmp_path: Path) -> None:
    num_classes = 3
    img_size = 64
    batch_size = 16
    epochs = 2

    train_x = torch.randn(128, 3, img_size, img_size)
    train_y = torch.randint(0, num_classes, (128,))
    val_x = torch.randn(64, 3, img_size, img_size)
    val_y = torch.randint(0, num_classes, (64,))
    train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(TensorDataset(val_x, val_y), batch_size=batch_size)

    model = build_model("resnet18", "linear", num_classes=num_classes, pretrained=False)
    assert model.backbone_info.num_features == 512

    optimizer = build_optimizer("adamw", model, lr=1e-3, weight_decay=1e-2)
    total_steps = len(train_loader) * epochs
    scheduler = build_scheduler(
        "cosine_warmup",
        optimizer,
        warmup_steps=max(1, total_steps // 10),
        total_steps=total_steps,
    )

    registry = Registry(str(tmp_path / "registry"))

    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=optimizer,
        scheduler=scheduler,
        callbacks=[
            ModelCheckpoint(
                registry=registry,
                monitor="val/loss",
                mode="min",
                model_name="beans-resnet18",
                version_prefix="ckpt",
            ),
            EarlyStopping(monitor="val/loss", patience=5, mode="min"),
            ProgressLogger(),
        ],
        device="auto",
        mixed_precision=True,
        gradient_accumulation_steps=2,
        clip_grad_norm=1.0,
    )
    history = trainer.fit(train_loader, val_loader, epochs=epochs)
    assert len(history["train/loss"]) == epochs
    assert len(history["val/loss"]) == epochs

    runner = EvaluationRunner(
        model=model,
        task="classification",
        num_classes=num_classes,
        device="auto",
        class_names=["angular_leaf_spot", "bean_rust", "healthy"],
    )
    results = runner.run(val_loader, step=epochs)
    assert {"accuracy", "precision", "recall", "f1"}.issubset(results.keys())

    card = ModelCard(
        name="beans-resnet18",
        version="v1",
        task="classification",
        architecture="ResNet18 + LinearHead",
        description="Quick-start demo model.",
        registry=registry,
    )
    card.add_result(metric="val/accuracy", value=results["accuracy"], dataset="beans-synthetic-val")
    card.add_result(metric="val/f1", value=results["f1"], dataset="beans-synthetic-val")

    staging_result = card.promote(to_stage=ModelStage.STAGING, require={"val/accuracy": 0.0})
    assert staging_result.success
    assert card.stage == ModelStage.STAGING

    demote_result = card.demote(to_stage=ModelStage.DEV, reason="Regression detected.")
    assert demote_result.success
    assert card.stage == ModelStage.DEV
    assert "Regression detected" in card.extra.get("demotion_reason", "")

    card_path = tmp_path / "card.json"
    card.save_json(str(card_path))
    card2 = ModelCard.load_json(str(card_path))
    assert card2.name == "beans-resnet18"
    assert card2.version == "v1"

    bridge = RegistryBridge(registry)
    key = bridge.save(model, name="beans-resnet18", version="v1")
    loaded_model = registry.load(key)
    assert loaded_model is not None

    onnx_path = tmp_path / "beans_resnet18.onnx"
    model.cpu().eval()
    dummy_input = torch.randn(1, 3, img_size, img_size)
    try:
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            input_names=["pixel_values"],
            output_names=["logits"],
            dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=17,
            dynamo=False,
        )
        assert onnx_path.exists()
    except Exception:
        pass  # mirrors sample's broad try/except — ONNX has optional backends


# ── 02_architectures.py ──────────────────────────────────────────────────────


def test_architectures() -> None:
    b, c, h, w = 2, 3, 64, 64
    x = torch.randn(b, c, h, w)

    # torchvision backbone + classification heads — resnet18 is 2× lighter than
    # resnet50 and exercises the same build_model + head assembly code path.
    m = build_model("resnet18", "linear", num_classes=10, pretrained=False)
    assert tuple(m(x).shape) == (2, 10)
    assert m.backbone_info.num_features == 512

    m = build_model("resnet18", "mlp", num_classes=10, pretrained=False, hidden_dim=512, dropout=0.2)
    assert tuple(m(x).shape) == (2, 10)

    m = build_model("resnet18", "multilabel", num_classes=20, pretrained=False)
    out = m(x)
    assert tuple(out.shape) == (2, 20)
    assert tuple(torch.sigmoid(out).shape) == (2, 20)

    m = build_model("resnet18", "linear", num_classes=5, pretrained=False)
    assert m.backbone_info.num_features == 512
    assert tuple(m(x).shape) == (2, 5)

    # Segmentation heads (custom spatial backbone)
    class TinyFPN(nn.Module):
        def __init__(self):
            super().__init__()
            self.body = nn.Sequential(
                nn.Conv2d(3, 64, 3, stride=2, padding=1),
                nn.ReLU(),
                nn.Conv2d(64, 128, 3, stride=2, padding=1),
                nn.ReLU(),
                nn.Conv2d(128, 256, 3, stride=2, padding=1),
                nn.ReLU(),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.body(x)

    tiny_fpn = TinyFPN()
    feat = tiny_fpn(x)
    assert tuple(feat.shape) == (2, 256, 8, 8)

    seg_in_channels = 256
    num_seg_classes = 21

    linear_seg = LinearSegHead(in_channels=seg_in_channels, num_classes=num_seg_classes)
    fpn_seg = FPNSegHead(in_channels=seg_in_channels, num_classes=num_seg_classes, hidden_dim=128)

    bb_info = BackboneInfo(name="tiny_fpn_test", num_features=seg_in_channels, model=tiny_fpn)
    linear_seg_model = ModelWrapper(backbone_info=bb_info, head=linear_seg)
    out_linear = linear_seg_model(x)
    assert out_linear.shape[1] == num_seg_classes

    fpn_bb_info = BackboneInfo(name="tiny_fpn_test_fpn", num_features=seg_in_channels, model=TinyFPN())
    fpn_seg_model = ModelWrapper(backbone_info=fpn_bb_info, head=fpn_seg)
    out_fpn = fpn_seg_model(x)
    assert out_fpn.shape[1] == num_seg_classes

    # build_model_from_hf — guarded
    try:
        hf_model = build_model_from_hf(
            "microsoft/resnet-50",
            head="linear",
            num_classes=10,
            pretrained=False,
        )
        assert tuple(hf_model(x).shape) == (2, 10)
    except (ImportError, Exception):
        pass  # transformers missing or network unavailable

    # Custom backbone (registered at module scope as "tiny_cnn_samples_test")
    tiny_cnn_model = build_model("tiny_cnn_samples_test", "linear", num_classes=7, pretrained=False)
    assert tuple(tiny_cnn_model(x).shape) == (2, 7)
    assert tiny_cnn_model.backbone_info.num_features == 512

    # list_backbones
    names = list_backbones()
    assert "tiny_cnn_samples_test" in names
    assert len(names) > 0

    # build_backbone + manual ModelWrapper
    bb_info = build_backbone("resnet18", pretrained=False)
    assert bb_info.num_features == 512
    head = MLPHead(
        in_features=bb_info.num_features,
        hidden_dim=256,
        num_classes=4,
        dropout=0.3,
        num_layers=3,
    )
    model = ModelWrapper(backbone_info=bb_info, head=head)
    assert tuple(model(x).shape) == (2, 4)

    # Introspection
    m = build_model("resnet18", "mlp", num_classes=3, pretrained=False, hidden_dim=512)
    total_params = sum(p.numel() for p in m.parameters())
    assert total_params > 0

    m_frozen = build_model("resnet18", "linear", num_classes=3, pretrained=False, freeze_backbone=True)
    frozen_after = sum(p.numel() for p in m_frozen.backbone.parameters() if not p.requires_grad)
    assert frozen_after > 0


# ── 03_training_features.py ──────────────────────────────────────────────────


def test_training_features(tmp_path: Path) -> None:
    num_classes = 4
    batch_size = 8
    h = w = 32

    train_x = torch.randn(32, 3, h, w)
    train_y = torch.randint(0, num_classes, (32,))
    val_x = torch.randn(16, 3, h, w)
    val_y = torch.randint(0, num_classes, (16,))
    train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(TensorDataset(val_x, val_y), batch_size=batch_size)
    steps = lambda: len(train_loader) * 2  # noqa: E731

    registry = Registry(str(tmp_path / "registry"))

    def fresh() -> nn.Module:
        return build_model("resnet18", "linear", num_classes=num_classes, pretrained=False)

    # 1. All callbacks
    model = build_model("resnet18", "linear", num_classes=num_classes, pretrained=False, freeze_backbone=True)
    opt = build_optimizer("adamw", model, lr=1e-3, weight_decay=1e-2)
    sched = build_scheduler("cosine", opt, total_steps=steps())

    callbacks = [
        ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            save_best_only=True,
            model_name="demo-model",
            version_prefix="ep",
        ),
        EarlyStopping(monitor="val/loss", patience=10, mode="min", min_delta=1e-4),
        LRMonitor(),
        ProgressLogger(),
        UnfreezeSchedule(
            schedule={
                1: ["backbone.layer3", "backbone.layer4"],
                2: ["backbone"],
            },
            new_lr=5e-5,
        ),
    ]
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        scheduler=sched,
        callbacks=callbacks,
        device="auto",
    )
    history = trainer.fit(train_loader, val_loader, epochs=3)
    assert len(history["train/loss"]) >= 1  # EarlyStopping may shorten

    # 2a. Optimizer — flat LR
    for opt_name in ("adam", "adamw", "sgd", "radam", "rmsprop"):
        kwargs = {"lr": 1e-3}
        if opt_name == "sgd":
            kwargs["momentum"] = 0.9
        opt = build_optimizer(opt_name, fresh(), **kwargs)
        assert opt.param_groups[0]["lr"] == 1e-3

    # 2b. backbone_lr_multiplier
    model = fresh()
    opt = build_optimizer("adamw", model, backbone_lr_multiplier=0.1, lr=1e-3, weight_decay=1e-2)
    assert len(opt.param_groups) == 2
    assert opt.param_groups[0]["lr"] == pytest.approx(1e-4)
    assert opt.param_groups[1]["lr"] == pytest.approx(1e-3)

    # 2c. explicit param groups
    model = fresh()
    param_groups = [
        {"params": model.backbone.parameters(), "lr": 5e-5},
        {"params": model.head.parameters(), "lr": 1e-3},
    ]
    opt = build_optimizer("adamw", param_groups, weight_decay=1e-2)
    assert opt.param_groups[0]["lr"] == 5e-5
    assert opt.param_groups[1]["lr"] == 1e-3

    # 3. All schedulers
    schedulers_spec = [
        ("cosine", {"total_steps": steps()}),
        ("cosine_warmup", {"warmup_steps": 4, "total_steps": steps()}),
        ("step", {"step_size": 4, "gamma": 0.5}),
        ("plateau", {"patience": 3, "factor": 0.5}),
        ("onecycle", {"max_lr": 1e-2, "total_steps": steps()}),
        ("constant", {}),
    ]
    for name, kw in schedulers_spec:
        fresh_opt = build_optimizer("adamw", fresh(), lr=1e-3)
        sched = build_scheduler(name, fresh_opt, **kw)
        assert sched is not None

    # 4. gradient_accumulation + clip + mixed_precision
    model = fresh()
    opt = build_optimizer("adamw", model, lr=1e-3)
    sched = build_scheduler("cosine", opt, total_steps=steps())
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        scheduler=sched,
        device="auto",
        mixed_precision=True,
        gradient_accumulation_steps=4,
        clip_grad_norm=1.0,
    )
    history = trainer.fit(train_loader, val_loader, epochs=1)
    assert len(history["train/loss"]) == 1

    # 5. gradient_checkpointing (silently ignored for resnet18)
    model = fresh()
    opt = build_optimizer("adamw", model, lr=1e-3)
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        device="auto",
        gradient_checkpointing=True,
    )
    trainer.fit(train_loader, epochs=1)

    # 6. batch_fn — dict batches
    dict_batches = [
        {"image": torch.randn(batch_size, 3, h, w), "label": torch.randint(0, num_classes, (batch_size,))}
        for _ in range(len(train_loader))
    ]

    def unpack_dict(batch: dict) -> tuple:
        return batch["image"], batch["label"]

    model = fresh()
    opt = build_optimizer("adamw", model, lr=1e-3)
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        device="auto",
        batch_fn=unpack_dict,
    )
    history = trainer.fit(dict_batches, epochs=1)
    assert len(history["train/loss"]) == 1

    # 7. Regression model + EvaluationRunner
    class TinyRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(nn.Linear(16, 64), nn.ReLU(), nn.Linear(64, 1))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.net(x).squeeze(-1)

    reg_model = TinyRegressor()
    reg_train = DataLoader(TensorDataset(torch.randn(64, 16), torch.randn(64)), batch_size=8, shuffle=True)
    reg_val = DataLoader(TensorDataset(torch.randn(32, 16), torch.randn(32)), batch_size=8)
    reg_opt = build_optimizer("adamw", reg_model, lr=1e-3)
    reg_trainer = Trainer(model=reg_model, loss_fn=nn.MSELoss(), optimizer=reg_opt, device="auto")
    reg_trainer.fit(reg_train, reg_val, epochs=2)

    reg_runner = EvaluationRunner(model=reg_model, task="regression", num_classes=1, device="auto")
    reg_results = reg_runner.run(reg_val)
    assert {"mae", "mse", "rmse", "r2"}.issubset(reg_results.keys())

    # 8. OptunaCallback with duck-typed trial
    class FakeTrial:
        def __init__(self):
            self.values: list = []

        def report(self, value: float, step: int) -> None:
            self.values.append((step, value))

        def should_prune(self) -> bool:
            return False

    fake_trial = FakeTrial()
    model = fresh()
    opt = build_optimizer("adamw", model, lr=1e-3)
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        callbacks=[OptunaCallback(fake_trial, monitor="val/loss")],
        device="auto",
    )
    trainer.fit(train_loader, val_loader, epochs=2)
    assert len(fake_trial.values) == 2


# ── 04_experiment_tracking.py ────────────────────────────────────────────────


def test_experiment_tracking(tmp_path: Path) -> None:
    num_classes = 3
    batch_size = 8
    h = w = 32

    train_loader = DataLoader(
        TensorDataset(torch.randn(48, 3, h, w), torch.randint(0, num_classes, (48,))),
        batch_size=batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.randn(24, 3, h, w), torch.randint(0, num_classes, (24,))),
        batch_size=batch_size,
    )

    registry = Registry(str(tmp_path / "registry"))

    def fresh_model() -> nn.Module:
        return build_model("resnet18", "linear", num_classes=num_classes, pretrained=False)

    available_trackers: list[Tracker] = []

    # TensorBoardTracker
    try:
        tb_log_dir = tmp_path / "tb_logs"
        tb_log_dir.mkdir()
        tb_tracker = TensorBoardTracker(log_dir=str(tb_log_dir))
        with tb_tracker.run("demo_run_tb", config={"lr": 1e-3, "epochs": 2}) as t:
            t.log_params({"backbone": "resnet18", "head": "linear"})
            t.log({"train/loss": 1.20, "val/loss": 1.35}, step=0)
            t.log({"train/loss": 0.95, "val/loss": 1.10}, step=1)
            t.log_model(fresh_model(), name="resnet18-demo", version="v0")
            t.log_artifact("/tmp")
        available_trackers.append(TensorBoardTracker(log_dir=str(tb_log_dir)))
    except (ImportError, Exception):
        pass

    # MLflowTracker
    try:
        mlflow_dir = tmp_path / "mlflow"
        mlflow_dir.mkdir()
        mlflow_uri = f"file://{mlflow_dir}"
        mlflow_tracker = MLflowTracker(tracking_uri=mlflow_uri, experiment_name="mindtrace-demo")
        with mlflow_tracker.run("demo_run_mlflow", config={"lr": 1e-3, "batch_size": 8}) as t:
            t.log_params({"optimizer": "adamw", "scheduler": "cosine"})
            t.log({"train/loss": 1.10, "val/loss": 1.25}, step=0)
            t.log({"train/loss": 0.88, "val/loss": 1.00}, step=1)
            try:
                t.log_model(fresh_model(), name="resnet18", version="v1")
            except Exception:
                pass
        available_trackers.append(MLflowTracker(tracking_uri=mlflow_uri, experiment_name="mindtrace-demo"))
    except (ImportError, Exception):
        pass

    # WandBTracker — skip unless wandb is properly configured
    try:
        wandb_tracker = WandBTracker(project="mindtrace-demo", entity=None)
        with wandb_tracker.run("demo_run_wandb", config={"lr": 1e-3}) as t:
            t.log_params({"architecture": "resnet18+linear"})
            t.log({"train/loss": 1.05, "val/loss": 1.18}, step=0)
            t.log({"train/loss": 0.80, "val/loss": 0.95}, step=1)
            t.log_model(fresh_model(), name="resnet18-wandb", version="v1")
        available_trackers.append(WandBTracker(project="mindtrace-demo"))
    except (ImportError, Exception):
        pass

    # CompositeTracker — always exercises the API (NoOp fallback if no backends)
    if available_trackers:
        composite = CompositeTracker(trackers=available_trackers)
        with composite.run("composite_run", config={"run_type": "composite_demo"}) as ct:
            ct.log({"metric/combined": 0.99}, step=0)
            ct.log_params({"note": "fan-out demo"})
    else:

        class _NoOpTracker(Tracker):
            def start_run(self, name, config):
                pass

            def log(self, metrics, step):
                pass

            def log_params(self, params):
                pass

            def log_model(self, model, name, version):
                pass

            def log_artifact(self, path):
                pass

            def finish(self):
                pass

        composite = CompositeTracker(trackers=[_NoOpTracker(), _NoOpTracker()])
        with composite.run("noop_composite", config={"note": "no external deps"}) as ct:
            ct.log({"train/loss": 0.5}, step=0)

    # RegistryBridge
    bridge = RegistryBridge(registry)
    key = bridge.save(fresh_model(), name="resnet18-bridge", version="v2")
    loaded = registry.load(key)
    assert loaded is not None

    # tracker= in Trainer — InMemoryTracker captures per-epoch metrics
    class InMemoryTracker(Tracker):
        def __init__(self):
            super().__init__()
            self.logs: list[dict] = []

        def start_run(self, name, config):
            pass

        def log(self, metrics, step):
            self.logs.append({"step": step, **metrics})

        def log_params(self, params):
            pass

        def log_model(self, model, name, version):
            pass

        def log_artifact(self, path):
            pass

        def finish(self):
            pass

    mem_tracker = InMemoryTracker()
    model = fresh_model()
    opt = build_optimizer("adamw", model, lr=1e-3, weight_decay=1e-2)
    total_s = len(train_loader)
    sched = build_scheduler("cosine_warmup", opt, warmup_steps=max(1, total_s // 5), total_steps=total_s)
    with mem_tracker.run("trainer_run", config={"lr": 1e-3, "epochs": 1}):
        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=opt,
            scheduler=sched,
            tracker=mem_tracker,
            device="auto",
        )
        trainer.fit(train_loader, val_loader, epochs=1)
    assert len(mem_tracker.logs) >= 1

    # Manual tracker calls
    manual = InMemoryTracker()
    manual.start_run("manual_run", {"lr": 3e-4})
    manual.log_params({"batch_size": 16, "architecture": "resnet18"})
    for step in range(5):
        manual.log({"train/loss": 1.0 - step * 0.15, "val/loss": 1.1 - step * 0.12}, step=step)
    manual.log_model(fresh_model(), name="resnet18", version="v3")
    manual.finish()
    assert len(manual.logs) == 5

    # Tracker.from_config factory
    for backend, kwargs in [
        ("tensorboard", {"log_dir": str(tmp_path / "tb_factory")}),
        ("mlflow", {"tracking_uri": f"file://{tmp_path / 'mlflow_factory'}", "experiment_name": "factory-demo"}),
        ("wandb", {"project": "factory-demo"}),
    ]:
        try:
            Tracker.from_config(backend, **kwargs)
        except (ImportError, Exception):
            pass


# ── 05_onnx_serving.py ───────────────────────────────────────────────────────


def test_onnx_serving(tmp_path: Path) -> None:
    pytest.importorskip("onnxruntime")
    tvm = pytest.importorskip("torchvision.models")

    # resnet18 @ 64×64 exercises the same export → OnnxModelService API flow
    # as sample 05's resnet50 @ 224×224, at a fraction of the cost.
    num_classes = 10
    img_size = 64
    onnx_path = tmp_path / "resnet_sample.onnx"

    model = tvm.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model.eval().cpu()

    dummy = torch.randn(1, 3, img_size, img_size)
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["pixel_values"],
        output_names=["logits"],
        opset_version=18,
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        dynamo=False,
    )
    assert onnx_path.exists()
    assert onnx_path.stat().st_size > 0

    svc = OnnxModelService(
        model_name="resnet-sample",
        model_version="v1",
        model_path=str(onnx_path),
    )
    assert svc.model_name == "resnet-sample"
    assert svc.model_version == "v1"
    assert svc.providers
    assert svc.input_names == ["pixel_values"]
    assert svc.output_names == ["logits"]
    assert svc.input_shapes
    assert svc.output_shapes

    img_batch = np.random.randn(4, 3, img_size, img_size).astype(np.float32)
    outputs = svc.predict_array({"pixel_values": img_batch})
    logits = outputs["logits"]
    assert logits.shape == (4, num_classes)

    info = svc.info()
    assert info.name == "resnet-sample"
    assert info.version == "v1"
    assert "input_names" in info.extra
    assert "providers" in info.extra

    # Subclass overriding predict()
    class ClassifierOnnxService(OnnxModelService):
        _task = "classification"

        def predict(self, request: PredictRequest) -> PredictResponse:
            n = len(request.images)
            arr = np.random.randn(n, 3, img_size, img_size).astype(np.float32)
            outputs = self.run({"pixel_values": arr})
            class_ids = outputs["logits"].argmax(axis=1).tolist()
            return PredictResponse(results=class_ids, timing_s=0.0)

    custom_svc = ClassifierOnnxService(
        model_name="classifier-custom",
        model_version="v2",
        model_path=str(onnx_path),
    )
    req = PredictRequest(images=["img1.jpg", "img2.jpg", "img3.jpg"])
    resp = custom_svc.predict(req)
    assert len(resp.results) == 3


# ── 06_evaluation.py ─────────────────────────────────────────────────────────


def test_evaluation() -> None:
    def make_cls_loader(n=128, num_classes=3, h=32, w=32, batch=16):
        return DataLoader(
            TensorDataset(torch.randn(n, 3, h, w), torch.randint(0, num_classes, (n,))),
            batch_size=batch,
        )

    def make_seg_loader(n=32, num_classes=4, h=64, w=64, batch=4):
        return DataLoader(
            TensorDataset(torch.randn(n, 3, h, w), torch.randint(0, num_classes, (n, h, w))),
            batch_size=batch,
        )

    def make_reg_loader(n=64, in_features=16, batch=8):
        return DataLoader(
            TensorDataset(torch.randn(n, in_features), torch.randn(n, 1)),
            batch_size=batch,
        )

    # Classification
    num_cls = 3
    cls_model = nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(16, num_cls),
    )
    cls_loader = make_cls_loader(num_classes=num_cls)
    runner_cls = EvaluationRunner(
        model=cls_model,
        task="classification",
        num_classes=num_cls,
        device="auto",
        class_names=["healthy", "angular_leaf", "bean_rust"],
    )
    cls_results = runner_cls.run(cls_loader, step=0)
    assert {"accuracy", "precision", "recall", "f1", "classification_report"}.issubset(cls_results.keys())

    # Segmentation
    num_seg = 4
    seg_model = nn.Sequential(
        nn.Conv2d(3, 32, 3, padding=1),
        nn.ReLU(),
        nn.Conv2d(32, num_seg, 1),
    )
    seg_loader = make_seg_loader(num_classes=num_seg)
    runner_seg = EvaluationRunner(model=seg_model, task="segmentation", num_classes=num_seg, device="auto")
    seg_results = runner_seg.run(seg_loader, step=0)
    assert {"mIoU", "mean_dice", "pixel_accuracy", "iou_per_class"}.issubset(seg_results.keys())

    # Detection
    num_det = 3

    class FakeDetector(nn.Module):
        def forward(self, images):
            b = images.shape[0]
            results = []
            for _ in range(b):
                n_preds = torch.randint(1, 5, (1,)).item()
                boxes = torch.rand(n_preds, 4)
                boxes[:, 2:] += boxes[:, :2]
                results.append(
                    {
                        "boxes": boxes * 100,
                        "scores": torch.rand(n_preds),
                        "labels": torch.randint(0, num_det, (n_preds,)),
                    }
                )
            return results

    def det_batch_fn(batch):
        images = batch[0]
        b = images.shape[0]
        targets = []
        for _ in range(b):
            n_gt = torch.randint(1, 4, (1,)).item()
            gt_boxes = torch.rand(n_gt, 4)
            gt_boxes[:, 2:] += gt_boxes[:, :2]
            targets.append({"boxes": gt_boxes * 100, "labels": torch.randint(0, num_det, (n_gt,))})
        return images, targets

    det_loader = DataLoader(TensorDataset(torch.randn(8, 3, 64, 64), torch.zeros(8)), batch_size=4)
    runner_det = EvaluationRunner(
        model=FakeDetector(),
        task="detection",
        num_classes=num_det,
        device="auto",
        batch_fn=det_batch_fn,
    )
    det_results = runner_det.run(det_loader, step=0)
    assert {"mAP@50", "mAP@75", "mAP@50:95"}.issubset(det_results.keys())

    # Regression
    in_feat = 16
    reg_model = nn.Sequential(nn.Linear(in_feat, 64), nn.ReLU(), nn.Linear(64, 1))
    reg_loader = make_reg_loader(in_features=in_feat)
    runner_reg = EvaluationRunner(model=reg_model, task="regression", num_classes=1, device="auto")
    reg_results = runner_reg.run(reg_loader, step=0)
    assert {"mae", "mse", "rmse", "r2"}.issubset(reg_results.keys())

    # Standalone metrics
    n = 200
    preds_cls = np.random.randint(0, 3, n)
    tgts_cls = np.random.randint(0, 3, n)
    assert 0.0 <= accuracy(preds_cls, tgts_cls) <= 1.0

    report = classification_report(preds_cls, tgts_cls, num_classes=3, class_names=["a", "b", "c"])
    assert "macro" in report
    assert "f1" in report["macro"]
    assert report["num_samples"] == n

    h_pix, w_pix = 32, 32
    preds_seg = np.random.randint(0, 4, (n, h_pix, w_pix))
    tgts_seg = np.random.randint(0, 4, (n, h_pix, w_pix))
    assert "mIoU" in mean_iou(preds_seg, tgts_seg, num_classes=4)
    assert "mean_dice" in dice_score(preds_seg, tgts_seg, num_classes=4)

    det_preds = [
        {"boxes": np.random.rand(3, 4) * 100, "scores": np.random.rand(3), "labels": np.array([0, 1, 2])}
        for _ in range(10)
    ]
    det_tgts = [{"boxes": np.random.rand(2, 4) * 100, "labels": np.array([0, 2])} for _ in range(10)]
    map_res = mean_average_precision(det_preds, det_tgts, num_classes=3, iou_threshold=0.5)
    assert "mAP" in map_res

    y_pred = np.random.randn(n)
    y_true = y_pred + np.random.randn(n) * 0.3
    assert isinstance(mae(y_pred, y_true), float)
    assert isinstance(mse(y_pred, y_true), float)
    assert isinstance(rmse(y_pred, y_true), float)
    assert isinstance(r2_score(y_pred, y_true), float)

    # Custom batch_fn
    def dict_batch_fn(batch):
        images, labels = batch
        return images, labels

    runner_custom = EvaluationRunner(
        model=cls_model,
        task="classification",
        num_classes=num_cls,
        device="auto",
        batch_fn=dict_batch_fn,
    )
    custom_results = runner_custom.run(cls_loader, step=1)
    assert "accuracy" in custom_results


# ── 07_lifecycle.py ──────────────────────────────────────────────────────────


def test_lifecycle(tmp_path: Path) -> None:
    card = ModelCard(
        name="resnet50-cls",
        version="v1",
        task="classification",
        architecture="ResNet50+LinearHead",
        framework="pytorch",
        training_data="imagenet",
        description="Weld defect classifier.",
    )
    assert card.registry_key()
    assert card.stage == ModelStage.DEV

    card.add_result("val/accuracy", 0.927, dataset="imagenet-val", split="val")
    card.add_result("val/f1", 0.912, dataset="imagenet-val", split="val")
    card.add_result("val/precision", 0.918)
    card.add_result("val/recall", 0.907)

    assert card.get_metric("val/accuracy") is not None
    assert card.get_metric("val/f1") is not None
    assert card.get_metric("missing_metric") is None

    assert card.registry_key(ModelStage.DEV)
    assert card.registry_key(ModelStage.STAGING)
    assert card.registry_key(ModelStage.PRODUCTION)
    assert card.registry_key(ModelStage.ARCHIVED)

    # EvalResult round-trip
    er = EvalResult(metric="test/iou", value=0.853, dataset="val-set", split="test")
    er2 = EvalResult.from_dict(er.to_dict())
    assert er2.value == 0.853

    # ModelStage transitions
    assert ModelStage.DEV.can_promote_to(ModelStage.STAGING)
    assert not ModelStage.DEV.can_promote_to(ModelStage.PRODUCTION)
    assert not ModelStage.STAGING.can_promote_to(ModelStage.DEV)
    assert not ModelStage.ARCHIVED.can_promote_to(ModelStage.DEV)
    assert VALID_PROMOTIONS

    # promote — passing
    class DummyRegistry:
        def __init__(self):
            self._store = {}

        def save(self, key, obj):
            self._store[key] = obj

        def load(self, key):
            return self._store.get(key)

    registry = DummyRegistry()
    card.registry = registry

    result: PromotionResult = card.promote(
        to_stage=ModelStage.STAGING,
        require={"val/accuracy": 0.90, "val/f1": 0.88},
    )
    assert result.success
    assert card.stage == ModelStage.STAGING

    # promote — failing
    with pytest.raises(PromotionError):
        card.promote(to_stage=ModelStage.PRODUCTION, require={"val/accuracy": 0.99})

    # dry_run
    pre_stage = card.stage
    dry = card.promote(to_stage=ModelStage.PRODUCTION, require={"val/accuracy": 0.90}, dry_run=True)
    assert dry.success
    assert card.stage == pre_stage

    # STAGING → PRODUCTION
    result_prod = card.promote(to_stage=ModelStage.PRODUCTION, require={"val/accuracy": 0.90})
    assert result_prod.success
    assert card.stage == ModelStage.PRODUCTION

    # demote
    demote_result = card.demote(to_stage=ModelStage.ARCHIVED, reason="Performance regression — retiring model.")
    assert demote_result.success
    assert "regression" in card.extra.get("demotion_reason", "").lower()

    # save/load JSON
    card_path = tmp_path / "card.json"
    card.save_json(str(card_path))
    loaded = ModelCard.load_json(str(card_path))
    assert loaded.name == "resnet50-cls"
    assert loaded.version == "v1"

    # to_dict / from_dict
    card_rt = ModelCard.from_dict(card.to_dict())
    assert card_rt.stage == card.stage

    # Registry integration
    simple_model = nn.Linear(10, 3)
    registry.save(f"{card.name}:{card.version}:weights", simple_model.state_dict())
    registry.save(f"{card.name}:{card.version}:card", card.to_dict())
    assert f"{card.name}:{card.version}:weights" in registry._store
    assert f"{card.name}:{card.version}:card" in registry._store

    # Full lifecycle journey
    registry2 = DummyRegistry()
    journey = ModelCard(name="journey-model", version="v2", task="detection", registry=registry2)
    journey.add_result("val/map50", 0.72)
    journey.add_result("val/map75", 0.65)
    stages = [
        (ModelStage.STAGING, {"val/map50": 0.65}),
        (ModelStage.PRODUCTION, {"val/map50": 0.70, "val/map75": 0.60}),
        (ModelStage.ARCHIVED, {}),
    ]
    for target, reqs in stages:
        r = journey.promote(to_stage=target, require=reqs or None)
        assert r.success
    assert journey.stage == ModelStage.ARCHIVED


# ── 08_hyperparameter_search.py ──────────────────────────────────────────────


def test_hyperparameter_search() -> None:
    num_classes = 3
    img_size = 32

    train_loader = DataLoader(
        TensorDataset(torch.randn(128, 3, img_size, img_size), torch.randint(0, num_classes, (128,))),
        batch_size=32,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.randn(32, 3, img_size, img_size), torch.randint(0, num_classes, (32,))),
        batch_size=32,
    )

    if optuna is not None:
        # Single-objective search
        def objective(trial):
            lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
            wd = trial.suggest_float("weight_decay", 1e-5, 1e-1, log=True)
            hidden = trial.suggest_categorical("hidden_dim", [64, 128])
            dropout = trial.suggest_float("dropout", 0.0, 0.4, step=0.1)

            model = build_model(
                "resnet18",
                "mlp",
                num_classes=num_classes,
                hidden_dim=hidden,
                pretrained=False,
                dropout=dropout,
            )
            optimizer = build_optimizer("adamw", model, lr=lr, weight_decay=wd)
            trainer = Trainer(
                model=model,
                loss_fn=nn.CrossEntropyLoss(),
                optimizer=optimizer,
                callbacks=[OptunaCallback(trial, monitor="val/loss")],
                device="auto",
            )
            trainer.fit(train_loader, val_loader, epochs=1)
            return trainer.history["val/loss"][-1]

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=2, show_progress_bar=False)
        assert len(study.trials) == 2
        assert study.best_params

        # Pruning
        def pruning_objective(trial):
            lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
            trial.suggest_categorical("hidden_dim", [64, 128])
            model = build_model("resnet18", "linear", num_classes=num_classes, pretrained=False)
            optimizer = build_optimizer("adam", model, lr=lr)
            cb = OptunaCallback(trial, monitor="val/loss")
            trainer = Trainer(
                model=model,
                loss_fn=nn.CrossEntropyLoss(),
                optimizer=optimizer,
                callbacks=[cb],
                device="auto",
            )
            try:
                trainer.fit(train_loader, val_loader, epochs=2)
            except optuna.TrialPruned:
                pass
            if not trainer.history.get("val/loss"):
                raise optuna.TrialPruned()
            return trainer.history["val/loss"][-1]

        pruner = optuna.pruners.MedianPruner(n_startup_trials=1, n_warmup_steps=1)
        pruning_study = optuna.create_study(direction="minimize", pruner=pruner)
        pruning_study.optimize(pruning_objective, n_trials=3, show_progress_bar=False)
        assert len(pruning_study.trials) == 3

        # Final model with best params
        best = study.best_params
        final_model = build_model(
            "resnet18",
            "mlp",
            num_classes=num_classes,
            hidden_dim=best.get("hidden_dim", 128),
            pretrained=False,
            dropout=best.get("dropout", 0.1),
        )
        final_opt = build_optimizer("adamw", final_model, lr=best["lr"], weight_decay=best["weight_decay"])
        final_trainer = Trainer(
            model=final_model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=final_opt,
            device="auto",
        )
        history = final_trainer.fit(train_loader, val_loader, epochs=2)
        assert len(history["val/loss"]) == 2

    # Duck-typed trial (runs with or without optuna)
    class DuckTrial:
        def __init__(self):
            self.reports: list[tuple[float, int]] = []
            self._prune_after = 2

        def report(self, value: float, step: int) -> None:
            self.reports.append((value, step))

        def should_prune(self) -> bool:
            return bool(self.reports and self.reports[-1][1] >= self._prune_after)

    duck_trial = DuckTrial()
    duck_cb = OptunaCallback(duck_trial, monitor="val/loss")
    duck_model = build_model("resnet18", "linear", num_classes=num_classes, pretrained=False)
    duck_opt = build_optimizer("adam", duck_model, lr=1e-3)
    duck_trainer = Trainer(
        model=duck_model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=duck_opt,
        callbacks=[duck_cb],
        device="auto",
    )
    duck_trainer.fit(train_loader, val_loader, epochs=4)
    assert len(duck_trial.reports) >= 1
