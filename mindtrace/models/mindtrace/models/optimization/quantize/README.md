# Quantization

> Make a model smaller and faster by storing its numbers with less precision.

## The idea in plain terms

A trained network stores its weights (the learned numbers) as **32-bit floating-point** values — very precise, but bulky. **Quantization** stores them as **8-bit integers** (INT8) instead. That's **4× smaller on disk and in memory**, and integer arithmetic is faster on most CPUs, GPUs and edge chips.

**Analogy:** imagine a shop's ledger that tracks every price to the exact cent. Round every price to the nearest dollar and the ledger gets smaller and the sums get faster to add up — and for most decisions the cents were never load-bearing. Quantization is that rounding, applied to a neural network's millions of numbers. The art is rounding where it doesn't matter and keeping precision where it does.

The trade-off is a small accuracy loss (often <1%). The three methods below trade *effort* against *how little accuracy you lose*.

## The three flavors

| Method | Needs data? | Needs retraining? | Accuracy loss | Use when |
|--------|:-----------:|:-----------------:|:-------------:|----------|
| **Dynamic PTQ** | No | No | Small–moderate | You want a quick win with zero setup |
| **Static PTQ** | ~200–500 sample images | No | Usually <1% | Production default for vision models |
| **QAT** | Full training set | Yes | Smallest | Static PTQ lost too much accuracy |

**PTQ** = *Post-Training Quantization* (quantize a model that's already trained).
**QAT** = *Quantization-Aware Training* (let the model practice being quantized while it trains).

### Dynamic PTQ — the free baseline

Weights become INT8; activations (the intermediate values) are quantized on the fly at run time. No calibration data needed.

```python
from mindtrace.models.optimization import quantize_dynamic

int8_path = quantize_dynamic("model.onnx")   # -> model-int8-dynamic.onnx, ~4x smaller
```

### Static PTQ — the production path

You feed a few hundred **representative** images through the model once so it can *measure* the typical range of every activation, then bake fixed INT8 scales into the graph. This is what OpenVINO / TensorRT / ONNX Runtime all consume.

```python
from mindtrace.models.optimization import StaticQuantizer

quantizer = StaticQuantizer(precision="int8", calibration_method="minmax")
int8_path = quantizer.run("model.onnx", calibration_loader, samples=256)
```

The calibration images should look like what the model sees in production — quantization measures *their* value ranges.

### QAT — quantization-aware training

Insert "fake quantization" during training so the network learns weights that survive INT8 rounding. It plugs into the existing `Trainer` as a callback — no new training loop.

```python
from mindtrace.models.training import Trainer
from mindtrace.models.optimization import QATCallback

qat = QATCallback(start_epoch=0)
trainer = Trainer(model=model, loss_fn=loss, optimizer=opt, callbacks=[qat])
trainer.fit(train_loader, val_loader, epochs=5)
int8_model = qat.convert()
```

## When INT8 costs too much accuracy

Not every layer tolerates quantization equally. Instead of giving up:

- **`sensitivity_scan`** quantizes one layer at a time and tells you which layers hurt the metric most.
- **`MixedPrecisionSearch`** keeps the few sensitive layers in higher precision and quantizes the rest, until an accuracy budget is met.

```python
from mindtrace.models.optimization import sensitivity_scan, MixedPrecisionSearch

report = sensitivity_scan("model.onnx", eval_fn, calibration_loader, top=12)
print(report.top(5))   # the 5 most quantization-sensitive nodes

search = MixedPrecisionSearch({"max_accuracy_drop": 0.01}, calibration_loader)
plan = search.run("model.onnx", eval_fn)   # excludes just enough nodes to hit the budget
```

## Honest notes

- **Smaller ≠ always faster.** INT8 only speeds up when the *runtime* fuses it into real integer kernels. On some CPU paths INT8 can be *slower* than FP32 — always [benchmark](../bench/README.md) on the actual target, and compile for it (see [compile](../compile/README.md)).
- Static PTQ needs realistic calibration data; random noise gives bad scales.

See the [optimization overview](../README.md) for how quantization fits into a full recipe.
