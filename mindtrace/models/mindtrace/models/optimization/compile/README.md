# Compilation

> Turn a portable model into a hardware-specific executable that runs as fast as the chip allows.

## The idea in plain terms

[Export](../export/README.md) gives you a portable ONNX file that runs *anywhere* — but not necessarily *fast* anywhere. **Compilation** takes that portable file and produces an executable tuned for **one specific piece of hardware**: it fuses operations together, picks the fastest kernel for each layer, and plans memory ahead of time.

**Analogy:** export is the **recipe** — readable by any cook. Compilation is the **meal prepped for your exact kitchen** — knowing your oven, your pans, your burners. The recipe travels; the prepped meal is for this kitchen only.

That last part is the key mental model:

> **Export produces one portable format. Compilation produces many hardware-specific formats — and those are not interchangeable.**

## Export vs compilation

| | Export | Compilation |
|--|--------|-------------|
| Output | ONNX (one portable file) | OpenVINO IR, TensorRT engine, ExecuTorch `.pte`, optimized ONNX |
| Runs on | Anything with an ONNX runtime | The one target it was built for |
| Optimizes for hardware? | No | Yes — fusion, kernel selection, memory planning |
| Portable? | Yes | **No** — a TensorRT engine built for one GPU won't run on another |

## Targets and backends

A **`TargetSpec`** names a deployment target (a chip + runtime + supported precisions). `compile_model` looks at the target's runtime and dispatches to the right backend:

```python
from mindtrace.models.optimization import compile_model, list_targets

print(list_targets())
# ort-cpu, ort-cuda, intel-cpu-openvino, intel-igpu-openvino,
# jetson-orin-nx, jetson-orin-nano, rpi5-cpu, executorch-generic, ...

# Intel CPU/iGPU -> OpenVINO IR (model.xml + model.bin)
artifact = compile_model("classifier-int8.onnx", "intel-cpu-openvino")

# NVIDIA Jetson -> TensorRT engine (.plan) — must be built ON the Jetson
artifact = compile_model("classifier-int8.onnx", "jetson-orin-nx")

# Phones / microcontrollers -> ExecuTorch (.pte)
artifact = compile_model(model, "executorch-generic")   # compiles from the torch model
```

Each returns a `CompiledArtifact` with the output path, the runtime, and metadata.

### What the backends do

- **ONNX Runtime (`ort`)** — graph-level optimization (still an `.onnx`, just fused/reordered). The lightest "compilation".
- **OpenVINO** — converts to Intel's IR format, optimized for Intel CPUs, iGPUs and NPUs.
- **TensorRT** — builds a serialized `.plan` engine for one NVIDIA GPU, with the best kernels for that exact device.
- **ExecuTorch** — lowers a torch program to a `.pte` for mobile/embedded runtimes (compiles from the model, not from ONNX).

## Why "build it where it runs"

TensorRT engines and NPU binaries are **device-specific** — you can't build them in CI and ship them around; they must be built on (or for) the exact target. That's the whole reason the serving layer ships a **compile agent** that runs on each edge box, pulls the portable ONNX, compiles locally, benchmarks, and stores the result. Portable ONNX travels; engines are built where they run.

## Honest notes

- **Compiling doesn't guarantee a speedup by itself** — an INT8 model may run faster under OpenVINO but slower under ONNX Runtime CPU. This is exactly why you [benchmark](../bench/README.md) each variant per target instead of assuming.
- TensorRT and NPU targets need their vendor toolchains present; the backends raise a clear error (pointing at the on-device compile agent) when they're missing.

See the [optimization overview](../README.md) for using `Compile` as the final step of a recipe.
