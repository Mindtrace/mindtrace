"""Edge optimization: compress, compile and benchmark models for edge deployment.

Sub-packages:
    quantize/  — dynamic PTQ, static PTQ with calibration, QAT, sensitivity analysis
    prune/     — structured channel pruning, magnitude pruning, pruning schedules
    export/    — ONNX export with simplification and parity checking
    compile/   — runtime compilation backends (ONNX Runtime, OpenVINO, TensorRT)
    bench/     — latency / memory / size benchmarking harness

Top-level modules:
    targets.py — TargetSpec registry describing deployment hardware
    recipes.py — declarative OptimizationRecipe (serializable pipeline of steps)
    runner.py  — OptimizationRunner (accuracy-aware recipe execution)

Heavy runtimes are optional: every backend guards its imports, so this package
is importable with none of the edge extras installed.
"""
