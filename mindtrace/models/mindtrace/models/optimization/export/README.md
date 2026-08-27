# Export

Convert a PyTorch model into a portable, framework-neutral file other runtimes can execute. A model in PyTorch is tied to Python and `torch`. To run it in a C++ inference server, on a phone, or under a vendor runtime from Intel or NVIDIA, export it to ONNX first: a single file describing the network's operations and weights as a computation graph, runnable without Python or PyTorch.

Export is the hub of the optimization pipeline. You export once to ONNX, then [quantize](../quantize/README.md), [compile](../compile/README.md) for specific hardware, and [benchmark](../bench/README.md), all from that one file.

## Formats

- ONNX: the portable interchange format produced here. Runnable by ONNX Runtime and consumed by every compiler downstream.
- Downstream, [compilation](../compile/README.md) converts ONNX into hardware-specific formats: OpenVINO IR (Intel), TensorRT engines (NVIDIA), ExecuTorch `.pte` (phones/microcontrollers). Those are not portable; each is built for one target. ONNX is the portable step they all start from.

## Exporting

A naive call to PyTorch's exporter can silently produce a graph that computes different numbers than the original (a bad op conversion, a control-flow quirk). `export_onnx` guards against that:

```python
from mindtrace.models.optimization import export_onnx, model_size_mb
import torch

path = export_onnx(
    model,
    "classifier.onnx",
    example_input=torch.randn(1, 3, 224, 224),
    opset=17,          # ONNX operator-set version to target
    simplify=True,     # onnxsim: fold constants, drop dead nodes
    check=True,        # verify ONNX output matches PyTorch within tolerance
)
print(model_size_mb(path))
```

- `check=True` runs the exported model through ONNX Runtime and compares its output against the original PyTorch model. On divergence it raises, so the bug surfaces here rather than on the device.
- `static_shape` vs `dynamic_batch`: pinning the input to a fixed shape (for example batch 1) usually runs measurably faster than leaving dimensions dynamic. Use a dynamic batch axis only when you need variable batch sizes.

```python
# Fixed shape, pinned batch of 1: the common edge case
export_onnx(model, "cls.onnx", static_shape=(1, 3, 224, 224), dynamic_batch=False)
```

## Notes

- `opset` selects the ONNX operator-set version. Newer opsets support more ops but require a runtime new enough to read them. 17 is a safe modern default.
- Keep `check=True` on unless you have a specific reason not to. It is the cheapest place to catch a numerical divergence.

See the [optimization overview](../README.md) for how export sits between the torch-side steps (prune/finetune) and the onnx-side steps (quantize/compile).
