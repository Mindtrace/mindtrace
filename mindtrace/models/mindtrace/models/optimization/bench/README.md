# Benchmarking

Measure latency, throughput, size, and memory of a model on real hardware. Every other technique in this package ([quantization](../quantize/README.md), [pruning](../prune/README.md), [compilation](../compile/README.md)) claims a smaller or faster model; benchmarking is how you confirm it. Intuition about neural-network speed is frequently wrong, so measure rather than assume.

## Running a benchmark

```python
from mindtrace.models.optimization import Benchmark

report = Benchmark(
    runtime="onnxruntime",          # torch | onnxruntime | openvino | callable
    artifact="classifier-int8.onnx",
    input_shape=(1, 3, 224, 224),
    warmup=10,                      # untimed runs to absorb one-time costs
    iterations=100,
).run()

print(report.table())
```

| Metric | Meaning | Why it matters |
|--------|---------|----------------|
| p50 latency | Median time for one inference | Typical-case speed |
| p95 latency | The time 95% of inferences beat | Real-time deadlines are set by the tail, not the mean |
| fps | Inferences per second (throughput) | Sustained processing rate |
| cold start | Time for the first inference, including load and setup | Relevant for on-demand services |
| size | Artifact size on disk | Deploy footprint |
| peak memory | Maximum RSS during the run | Whether it fits alongside other processes |

Two run modes:

- `warmup` runs are excluded from the statistics. The first inferences pay one-time costs (kernel compilation, memory-arena growth) that would skew the average.
- `sustained_seconds` runs for a wall-clock window instead of a fixed iteration count. This exposes thermal throttling: a Jetson that is fast for one burst may slow once it heats up. Burst benchmarks miss that; sustained runs catch it.

## Comparing variants

The point of the harness is a side-by-side: FP32 vs INT8 vs pruned+INT8 vs OpenVINO-compiled.

```python
from mindtrace.models.optimization import Benchmark, BenchmarkReport

reports = [
    Benchmark(runtime="torch", artifact=torch_model, input_shape=(1, 3, 224, 224)).run(),
    Benchmark(runtime="onnxruntime", artifact="fp32.onnx", input_shape=(1, 3, 224, 224)).run(),
    Benchmark(runtime="onnxruntime", artifact="int8.onnx", input_shape=(1, 3, 224, 224)).run(),
]
print(BenchmarkReport.compare(reports))   # one column per variant
report.log_to(tracker)                    # forward metrics to an experiment tracker
```

## Notes

- Smaller is not always faster. INT8 under ONNX Runtime CPU can be slower than FP32 for some models, while the same INT8 file under OpenVINO is the fastest of the set. Only the table tells you which to ship.
- Benchmark on the target device, not your workstation. Latency depends on the exact chip, its caches, and its thermal behavior.

`OptimizationRunner` uses this harness for its `p95_latency_ms` / `max_size_mb` gates. See the [optimization overview](../README.md).
