# Compilation

Turn a portable ONNX model into a hardware-specific executable. [Export](../export/README.md) produces one ONNX file that runs anywhere an ONNX runtime exists, but not necessarily fast anywhere. Compilation takes that file and produces an artifact tuned for one target: it fuses operations, selects the fastest kernel per layer, and plans memory ahead of time.

The key distinction: export produces one portable format; compilation produces many hardware-specific formats, and those are not interchangeable.

## Export vs compilation

| | Export | Compilation |
|--|--------|-------------|
| Output | ONNX (one portable file) | OpenVINO IR, TensorRT engine, ExecuTorch `.pte`, optimized ONNX |
| Runs on | Anything with an ONNX runtime | Only the target it was built for |
| Hardware-specific optimization | No | Yes: fusion, kernel selection, memory planning |
| Portable | Yes | No. A TensorRT engine built for one GPU will not run on another |

## Targets and backends

A `TargetSpec` names a deployment target: a chip, a runtime, and its supported precisions. `compile_model` reads the target's runtime and dispatches to the matching backend.

```python
from mindtrace.models.optimization import compile_model, list_targets

print(list_targets())
# executorch-generic, hailo-8, intel-cpu-openvino, intel-igpu-openvino,
# jetson-orin-nano, jetson-orin-nx, ort-cpu, ort-cuda, rknn-3588, rpi5-cpu

# Intel CPU/iGPU -> OpenVINO IR (model.xml + model.bin)
artifact = compile_model("classifier-int8.onnx", "intel-cpu-openvino")

# NVIDIA Jetson -> TensorRT engine, built ON the Jetson
artifact = compile_model("classifier-int8.onnx", "jetson-orin-nx")

# Phones / microcontrollers -> ExecuTorch, compiled from the torch model
artifact = compile_model(model, "executorch-generic")
```

Each call returns a `CompiledArtifact` with the output path, runtime, and metadata.

### Backends

- ONNX Runtime (`ort`): graph-level optimization. Output is still an `.onnx`, fused and reordered. The lightest form of compilation.
- OpenVINO: converts to Intel's IR, optimized for Intel CPUs, iGPUs, and NPUs.
- TensorRT: builds a serialized engine for one NVIDIA GPU with the best kernels for that device. If the parser rejects a graph over redundant nodes (for example, those left by a LoRA merge), it is simplified with `onnxsim` and parsed once more before failing.
- ExecuTorch: lowers a torch program to a `.pte` for mobile and embedded runtimes. Compiles from the model, not from ONNX.

## Build it where it runs

TensorRT engines and NPU binaries are device-specific. You cannot build them in CI and ship them around; they must be built on (or for) the exact target. This is why the serving layer ships a compile agent that runs on each edge box, pulls the portable ONNX, compiles locally, benchmarks, and stores the result.

## Notes

- Compiling does not guarantee a speedup. An INT8 model may run faster under OpenVINO but slower under ONNX Runtime CPU, so [benchmark](../bench/README.md) each variant per target.
- TensorRT and NPU targets need their vendor toolchains present. The backends raise a clear error pointing at the on-device compile agent when they are missing.

See the [optimization overview](../README.md) for using `Compile` as the final step of a recipe.
