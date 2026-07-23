# Benchmarking

> Measure how fast and how big a model actually is — because optimization only counts if you can prove it.

## The idea in plain terms

Every technique in this package — [quantization](../quantize/README.md), [pruning](../prune/README.md), [compilation](../compile/README.md) — *claims* to make a model smaller or faster. **Benchmarking** is how you check whether it actually did, on real hardware. You run the model many times and record what happened.

**Analogy:** a stopwatch and a scale. You wouldn't trust "this recipe is faster" without timing it; you don't trust "this model is faster" without measuring it. Neural-network intuition about speed is frequently wrong, so the rule is simple: **measure, don't assume.**

## What the numbers mean

```python
from mindtrace.models.optimization import Benchmark

report = Benchmark(
    runtime="onnxruntime",          # torch | onnxruntime | openvino | callable
    artifact="classifier-int8.onnx",
    input_shape=(1, 3, 224, 224),
    warmup=10,                      # untimed runs first (the first few are always slow)
    iterations=100,
).run()

print(report.table())
```

| Metric | Plain meaning | Why it matters |
|--------|---------------|----------------|
| **p50 latency** | The *typical* time for one inference (median) | Your everyday speed |
| **p95 latency** | The time 95% of inferences beat (near worst-case) | Real-time deadlines are set by the slow ones, not the average |
| **fps** | Inferences per second (throughput) | How many frames/parts you can process |
| **cold start** | Time for the *very first* inference (loading + setup) | Matters for services that spin up on demand |
| **size** | Artifact size on disk | Fits the device? Faster to ship? |
| **peak memory** | Most RAM used during the run | Fits alongside other models on the box? |

Two modes worth knowing:

- **`warmup`** runs are excluded from the timing — the first inferences pay one-time costs (kernel compilation, memory-arena growth) and would skew the average.
- **`sustained_seconds`** keeps running for a wall-clock window instead of a fixed count. This exposes **thermal throttling** — a Jetson that's fast for one burst may slow down once it heats up. Burst benchmarks hide that; sustained ones reveal it.

## Comparing variants

The real value is a side-by-side: FP32 vs INT8 vs pruned+INT8 vs OpenVINO-compiled.

```python
from mindtrace.models.optimization import Benchmark, BenchmarkReport

reports = [
    Benchmark(runtime="torch", artifact=torch_model, input_shape=(1, 3, 224, 224)).run(),
    Benchmark(runtime="onnxruntime", artifact="fp32.onnx", input_shape=(1, 3, 224, 224)).run(),
    Benchmark(runtime="onnxruntime", artifact="int8.onnx", input_shape=(1, 3, 224, 224)).run(),
]
print(BenchmarkReport.compare(reports))   # one column per variant
report.log_to(tracker)                    # or send metrics to an experiment tracker
```

## Honest notes

- This is where "smaller is always faster" gets disproven: INT8 under ONNX Runtime CPU can be *slower* than FP32 for some models, while the same INT8 file under OpenVINO is the fastest of all. Only the benchmark table tells you which to actually ship.
- Benchmark on the **target device**, not your workstation — latency depends on the exact chip, its caches, and its thermal behavior.

The `OptimizationRunner` uses this harness automatically for its `p95_latency_ms` / `max_size_mb` gates — see the [optimization overview](../README.md).
