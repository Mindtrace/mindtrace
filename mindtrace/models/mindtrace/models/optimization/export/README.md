# Export

> Turn a Python/PyTorch model into a portable file other runtimes can run.

## The idea in plain terms

A model living in PyTorch is tied to Python and the `torch` library. To run it somewhere else — a C++ inference server, a phone, an industrial camera box, a runtime written by Intel or NVIDIA — you first **export** it to a portable, framework-neutral format.

The standard format is **ONNX** (*Open Neural Network Exchange*): a single file that describes the network's operations and weights as a computation graph, runnable by many engines **without Python or PyTorch**.

**Analogy:** exporting a document to **PDF**. Your word processor's `.docx` only opens well in that word processor; a PDF opens anywhere. ONNX is the PDF of neural networks — one file, many readers.

Export is the **hub** of the whole optimization pipeline: you export once to ONNX, then [quantize](../quantize/README.md) it, [compile](../compile/README.md) it for specific hardware, and [benchmark](../bench/README.md) it — all from that one portable file.

## What "export formats" means

- **ONNX** — the portable interchange format produced here. Runnable by ONNX Runtime, and consumed by every compiler below.
- Downstream, [compilation](../compile/README.md) converts that ONNX into **hardware-specific** formats: OpenVINO **IR** (Intel), TensorRT **engines** (NVIDIA), ExecuTorch **`.pte`** (phones/microcontrollers). Those are *not* portable — each is built for one target. ONNX is the portable middle step they all start from.

## Doing it right

Naively calling PyTorch's exporter can silently produce a graph that computes *different* numbers than the original (a bad op conversion, a control-flow quirk). `export_onnx` guards against that:

```python
from mindtrace.models.optimization import export_onnx, model_size_mb
import torch

path = export_onnx(
    model,
    "classifier.onnx",
    example_input=torch.randn(1, 3, 224, 224),
    opset=17,          # ONNX operator-set version to target
    simplify=True,     # onnxsim: fold constants, drop dead nodes -> smaller, cleaner graph
    check=True,        # verify the ONNX output matches PyTorch within tolerance
)
print(model_size_mb(path))
```

Two knobs worth knowing:

- **`check=True`** runs the exported model through ONNX Runtime and compares its output against the original PyTorch model. If they diverge, export raises — you find the bug now, not on the device.
- **`static_shape` vs `dynamic_batch`** — pinning the input to a fixed shape (e.g. batch size 1) usually runs measurably faster than leaving dimensions dynamic. Use a dynamic batch axis only when you actually need variable batch sizes.

```python
# Fixed shape, pinned batch of 1 — the common edge case
export_onnx(model, "cls.onnx", static_shape=(1, 3, 224, 224), dynamic_batch=False)
```

## Honest notes

- **`opset`** is the ONNX operator-set version; newer opsets support more ops but need a runtime new enough to read them. 17 is a safe modern default.
- Export is where a subtle model bug surfaces loudly — keep `check=True` on unless you have a specific reason not to.

See the [optimization overview](../README.md) for how export sits between the torch-side steps (prune/finetune) and the onnx-side steps (quantize/compile).
