# Quantization

Shrink and speed up a model by storing its numbers at lower precision. A trained network stores weights as 32-bit floats. Quantization stores them as 8-bit integers (INT8): 4x smaller on disk and in memory, and integer arithmetic is faster on most CPUs, GPUs, and edge chips. The cost is a small accuracy loss, often under 1%. The methods below trade effort against how little accuracy is lost.

## The three methods

| Method | Needs data? | Needs retraining? | Accuracy loss | Use when |
|--------|:-----------:|:-----------------:|:-------------:|----------|
| Dynamic PTQ | No | No | Small to moderate | Quick baseline, zero setup |
| Static PTQ | ~200-500 samples | No | Usually <1% | Production default for vision models |
| QAT | Full training set | Yes | Smallest | Static PTQ lost too much accuracy |

PTQ is post-training quantization (quantize an already-trained model). QAT is quantization-aware training (the model trains with quantization simulated in the forward pass).

### Dynamic PTQ

Weights become INT8; activations are quantized on the fly at run time. No calibration data.

```python
from mindtrace.models.optimization import quantize_dynamic

int8_path = quantize_dynamic("model.onnx")   # -> model-int8-dynamic.onnx
```

### Static PTQ

Feed a few hundred representative samples through the model once to measure the range of every activation, then bake fixed INT8 scales into the graph. This is what OpenVINO, TensorRT, and ONNX Runtime consume.

```python
from mindtrace.models.optimization import StaticQuantizer

quantizer = StaticQuantizer(precision="int8", calibration_method="minmax")
int8_path = quantizer.run("model.onnx", calibration_loader, samples=256)
```

Calibration data should match production inputs; quantization measures their value ranges.

### QAT for CNNs

`QATCallback` inserts fake quantization during training via FX graph mode, so the network learns weights that survive INT8 rounding. It plugs into the existing `Trainer` as a callback.

```python
from mindtrace.models.training import Trainer
from mindtrace.models.optimization import QATCallback

qat = QATCallback(start_epoch=0)
trainer = Trainer(model=model, loss_fn=loss, optimizer=opt, callbacks=[qat])
trainer.fit(train_loader, val_loader, epochs=5)
int8_model = qat.convert()
```

### Module-level QAT (transformers)

FX graph mode does not trace models with dynamic control flow. For those, including transformers, the module-level path swaps target layers for fake-quant wrappers by class name, with no tracing. `prepare_qat` inserts the wrappers, you train or run calibration forwards to populate activation scales, and `convert_qat` produces the deployed INT8 model. The `QuantScheme` (bit-widths, per-channel weights, target layer types) rides with the converted module, so a saved model is self-describing.

```python
from mindtrace.models.optimization import (
    QuantScheme, prepare_qat, convert_qat, export_quantized_onnx, quantization_manifest,
)

scheme = QuantScheme.int8()                 # or QuantScheme(weight_bits=8, target_types=("Linear",))
model = prepare_qat(model, scheme)          # in place; swaps target layers for fake-quant wrappers
trainer.fit(train_loader, val_loader, epochs=3)

deployed = convert_qat(model)               # FakeQuantLinear -> QuantizedLinear, scales frozen
print(quantization_manifest(deployed))      # per-layer scheme + scales, JSON-able
export_quantized_onnx(deployed, "model-int8.onnx", example_input=example)  # QDQ ONNX carrying QAT scales
```

## When INT8 costs too much accuracy

Not every layer tolerates quantization equally.

- `sensitivity_scan` quantizes one candidate node at a time and ranks them by metric impact.
- `MixedPrecisionSearch` keeps the sensitive layers in higher precision and quantizes the rest until an accuracy budget is met.

```python
from mindtrace.models.optimization import sensitivity_scan, MixedPrecisionSearch

report = sensitivity_scan("model.onnx", eval_fn, calibration_loader, top=12)
print(report.top(5))   # the 5 most quantization-sensitive nodes

search = MixedPrecisionSearch({"max_accuracy_drop": 0.01}, calibration_loader)
plan = search.run("model.onnx", eval_fn)   # excludes the minimum nodes needed to hit the budget
```

## Notes

- Smaller is not always faster. INT8 speeds up only when the runtime fuses it into real integer kernels. On some CPU paths INT8 is slower than FP32, so [benchmark](../bench/README.md) on the target and [compile](../compile/README.md) for it.
- Static PTQ needs realistic calibration data; random noise produces bad scales.

See the [optimization overview](../README.md) for how quantization fits into a full recipe.
