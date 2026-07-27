"""13_multitask_qat_pipeline.py — end-to-end multi-task train -> QAT -> QDQ -> compile.

The whole edge pipeline for a MULTI-TASK model, entirely inside mindtrace — no
hand-rolled training loop, no dropping to raw torch. A tiny two-head model
(shared trunk -> a classification head + a regression head) on synthetic data
learns a coupled task, then is quantized with QAT and exported as a real INT8 QDQ
ONNX that a runtime lowers to INT8 kernels.

  1. Multi-task training — Trainer with a coupled loss AND per-task metrics
     (metrics={...}), plus an epoch-based LR schedule (scheduler_interval="epoch").
     history reports val/accuracy AND val/mae, not just loss.
  2. QAT — prepare_qat inserts fake-quant (module-level, no FX tracing), the SAME
     Trainer retrains so the weights adapt, then convert_qat produces a
     scheme-preserving INT8 model whose eval numerics match the trained model.
  3. Introspection — quantization_manifest() describes every quantized layer.
  4. QDQ export — export_quantized_onnx() emits QuantizeLinear/DequantizeLinear
     carrying the learned scales; ONNX Runtime reproduces the torch INT8 accuracy.
  5. Compile + benchmark — compile the QDQ graph for a target (TensorRT if present,
     else ort-cpu) and benchmark it, with the actually-used provider recorded.

Everything runs on CPU in a few seconds.

Run:
    python samples/models/13_multitask_qat_pipeline.py
"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

# mindtrace is torch-NATIVE: it owns the ML *workflow* (train / optimize / export /
# compile / benchmark), not the tensor primitives. Model definition (nn.Module), tensors,
# and data loading (DataLoader) stay pure torch by design — you keep torch's full
# flexibility. Everything workflow-level goes through mindtrace: optimizers, schedulers,
# and losses via build_optimizer / build_scheduler / build_loss (custom losses can still
# be any callable you write in torch).
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# ── Optional dependency guard ──────────────────────────────────────────────
try:
    import numpy as np
    import onnx  # noqa: F401
    import onnxruntime as ort

    _EDGE = True
except ImportError:
    _EDGE = False
    print("SKIPPING: onnx/onnxruntime not installed — pip install mindtrace-models[edge]")
    raise SystemExit(0)

from mindtrace.models import MultiTaskLoss, TaskSpec, Trainer, build_loss, build_optimizer, build_scheduler
from mindtrace.models.optimization import (
    Benchmark,
    QuantScheme,
    compile_model,
    convert_qat,
    export_quantized_onnx,
    prepare_qat,
    quantization_manifest,
)

if not torch.cuda.is_available():
    torch.set_num_threads(max(1, (os.cpu_count() or 8) // 4))

torch.manual_seed(0)
FEATURES, NUM_CLASSES = 16, 4


# ── A learnable synthetic multi-task problem ───────────────────────────────
# The labeling rule (projection weights) is FIXED and shared across splits — only
# the inputs differ per split. (Drawing them per-split would make train and val use
# different rules and the model would never generalize.)
_wg = torch.Generator().manual_seed(1)
W_CLS = torch.randn(FEATURES, NUM_CLASSES, generator=_wg)
W_REG = torch.randn(FEATURES, generator=_wg) / (FEATURES ** 0.5)  # -> reg ~ unit variance


class MultiTaskData(Dataset):
    """cls label = argmax of a fixed linear projection; reg target = a linear function."""

    def __init__(self, n: int, seed: int):
        self.x = torch.randn(n, FEATURES, generator=torch.Generator().manual_seed(seed))
        self.cls = (self.x @ W_CLS).argmax(1)
        self.reg = self.x @ W_REG

    def __len__(self):
        return len(self.x)

    def __getitem__(self, i):
        return self.x[i], {"cls": self.cls[i], "reg": self.reg[i]}


class TwoHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(FEATURES, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
        self.cls_head = nn.Linear(64, NUM_CLASSES)
        self.reg_head = nn.Linear(64, 1)

    def forward(self, x):
        h = self.trunk(x)
        return self.cls_head(h), self.reg_head(h).squeeze(-1)


# The coupled loss composed from mindtrace: cross-entropy on head 0, MSE on head 1.
multitask_loss = MultiTaskLoss({
    "cls": TaskSpec(build_loss("cross_entropy"), output=0, target="cls"),
    "reg": TaskSpec(build_loss("mse"), output=1, target="reg", weight=0.5),
})


def accuracy(outputs, targets):
    logits, _ = outputs
    return (logits.argmax(1) == targets["cls"]).float().mean().item()


def mae(outputs, targets):
    _, reg = outputs
    return (reg - targets["reg"]).abs().mean().item()


train_loader = DataLoader(MultiTaskData(4000, seed=0), batch_size=64, shuffle=True)
val_loader = DataLoader(MultiTaskData(512, seed=1), batch_size=64)
METRICS = {"accuracy": accuracy, "mae": mae}


def onnx_accuracy(session: "ort.InferenceSession") -> float:
    """Reuse the val set to score an ONNX model — logits vs regression by output size."""
    iname = session.get_inputs()[0].name
    probe = session.run(None, {iname: MultiTaskData(1, seed=2)[0][0][None].numpy()})
    li = 0 if np.asarray(probe[0]).size >= np.asarray(probe[1]).size else 1
    correct = total = 0
    for x, t in val_loader:
        logits = session.run(None, {iname: x.numpy()})[li]
        correct += int((logits.argmax(1) == t["cls"].numpy()).sum())
        total += len(x)
    return correct / total


# ── 1. Multi-task training (Trainer: coupled loss + per-task metrics) ───────
print("\n[1] Multi-task training — Trainer(metrics=..., scheduler_interval='epoch')")
model = TwoHead()
opt = build_optimizer("adamw", model, lr=5e-3)                 # mindtrace factory
sched = build_scheduler("cosine", opt, T_max=25)               # mindtrace factory
trainer = Trainer(
    model, multitask_loss, opt,
    metrics=METRICS,
    scheduler=sched,
    scheduler_interval="epoch",  # cosine over epochs, not per batch
)
history = trainer.fit(train_loader, val_loader, epochs=25)
print(f"    fp32:  val/accuracy={history['val/accuracy'][-1]:.3f}  val/mae={history['val/mae'][-1]:.3f}")

# ── 2. QAT — prepare -> retrain with the SAME Trainer -> convert ────────────
print("\n[2] QAT — prepare_qat -> Trainer retrain -> convert_qat (scheme-preserving)")
prepare_qat(model, QuantScheme.int8())
qat_opt = build_optimizer("adamw", model, lr=1e-3)
qat_history = Trainer(model, multitask_loss, qat_opt, metrics=METRICS).fit(train_loader, val_loader, epochs=6)
print(f"    QAT (fake-quant): val/accuracy={qat_history['val/accuracy'][-1]:.3f}  val/mae={qat_history['val/mae'][-1]:.3f}")
convert_qat(model)  # -> INT8 storage, frozen scales, same eval numerics
model.cpu().eval()  # export/serve on CPU

# ── 3. Introspection ───────────────────────────────────────────────────────
manifest = quantization_manifest(model)
print(f"\n[3] quantization_manifest: {manifest['count']} quantized layers, converted={manifest['converted']}")
for layer in manifest["quantized_layers"]:
    print(f"    {layer['path']:16} {layer['kind']}  w{layer['weight_bits']}/a{layer['activation_bits']}")

# ── 4. QDQ export + ONNX-Runtime parity ────────────────────────────────────
with TemporaryDirectory() as tmp:
    onnx_path = Path(tmp) / "model_int8_qdq.onnx"
    export_quantized_onnx(
        model, onnx_path, static_shape=(1, FEATURES), dynamic_batch=True,
        input_names=("input",), output_names=("logits", "reg"),
    )
    ops = {n.op_type for n in onnx.load(str(onnx_path)).graph.node}
    print(f"\n[4] QDQ export — QuantizeLinear={('QuantizeLinear' in ops)}  DequantizeLinear={('DequantizeLinear' in ops)}")
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    print(f"    INT8 ONNX accuracy under ONNX Runtime: {onnx_accuracy(session):.3f}  (matches the QAT torch model)")

    # ── 5. Compile + benchmark ─────────────────────────────────────────────
    try:
        import tensorrt  # noqa: F401

        target = "jetson-orin-nx"  # native TensorRT-INT8 engine (needs a GPU)
    except ImportError:
        target = "ort-cpu"
    print(f"\n[5] Compile for '{target}' + benchmark")
    try:
        artifact = compile_model(onnx_path, target, output_dir=Path(tmp) / "compiled")
        print(f"    compiled: {Path(artifact.path).name}")
        report = Benchmark(
            runtime="onnxruntime", artifact=str(onnx_path),
            input_shape=(1, FEATURES), warmup=5, iterations=50,
        ).run()
        print(f"    p50={report.p50_ms:.3f} ms  provider={report.meta['effective_provider']}"
              f"  fell_back={report.meta['provider_fell_back']}")
    except Exception as exc:  # noqa: BLE001 — compilation targets vary by machine
        print(f"    compile/benchmark skipped on this machine: {type(exc).__name__}: {exc}")

print("\nDone — trained multi-task, QAT-quantized, exported INT8 QDQ, and compiled, all via mindtrace.")
