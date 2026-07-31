"""Coverage-raising unit tests for optimization.bench.benchmark and quantize.ptq.

Targets previously-uncovered helper/edge/error branches:

benchmark.py: _percentile single-value, _peak_rss_mb, _current_rss_mb failure,
  _RssSampler ru_maxrss fallback, _file_size_mb .xml+.bin, iterations/warmup
  validation, openvino runner (mocked), torch integer-dtype input, onnxruntime
  ImportError, callable non-callable, integer _numpy_input.

ptq.py: _require_ort_quant ImportError, _resolve_input_info initializer skip /
  no-input raise, _resolve_input_name, _batch_to_arrays layout branches,
  collect_feeds dict-break / empty raise, FeedCalibrationReader.rewind,
  preprocess_for_quantization exception fallback, StaticQuantizer FileNotFound.

Everything runs offline on CPU; heavy runtimes are mocked / monkeypatched.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


from mindtrace.models.optimization.bench import benchmark as bench  # noqa: E402
from mindtrace.models.optimization.bench.benchmark import (  # noqa: E402
    Benchmark,
    _current_rss_mb,
    _file_size_mb,
    _peak_rss_mb,
    _percentile,
    _RssSampler,
)
from mindtrace.models.optimization.quantize import ptq  # noqa: E402
from mindtrace.models.optimization.quantize.ptq import (  # noqa: E402
    FeedCalibrationReader,
    StaticQuantizer,
    _batch_to_arrays,
    _resolve_input_info,
    _resolve_input_name,
    collect_feeds,
    preprocess_for_quantization,
)


# ===========================================================================
# benchmark.py module-level helpers
# ===========================================================================


class TestBenchmarkHelpers:
    def test_percentile_single_value(self) -> None:
        # Line 75: single-element list short-circuits to its only value.
        assert _percentile([4.2], 0.95) == 4.2

    def test_percentile_interpolates(self) -> None:
        assert _percentile([0.0, 10.0], 0.5) == pytest.approx(5.0)

    def test_peak_rss_mb_positive(self) -> None:
        # Lines 93-95.
        assert _peak_rss_mb() > 0

    def test_current_rss_mb_handles_open_failure(self, monkeypatch) -> None:
        # Lines 108-109: an OSError reading /proc yields None.
        import builtins

        real_open = builtins.open

        def boom(path, *args, **kwargs):
            if str(path) == "/proc/self/statm":
                raise OSError("no proc here")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", boom)
        assert _current_rss_mb() is None

    def test_rss_sampler_ru_maxrss_fallback(self) -> None:
        # Lines 140-142: when method is not "statm", __exit__ records ru_maxrss.
        sampler = _RssSampler()
        sampler.method = "ru_maxrss"  # force the fallback branch
        with sampler:
            pass
        assert sampler.method == "ru_maxrss"
        assert sampler.max_rss_mb > 0

    def test_file_size_mb_includes_xml_bin_sibling(self, tmp_path: Path) -> None:
        # Lines 167-169: .xml artifact adds sibling .bin weights size.
        xml = tmp_path / "model.xml"
        xml.write_bytes(b"x" * 1024)
        bin_ = tmp_path / "model.bin"
        bin_.write_bytes(b"y" * (2 * 1024 * 1024))
        size = _file_size_mb(xml)
        assert size == pytest.approx((1024 + 2 * 1024 * 1024) / (1024.0 * 1024.0))

    def test_file_size_mb_xml_without_bin(self, tmp_path: Path) -> None:
        # .xml with no sibling .bin: the exists() guard is False.
        xml = tmp_path / "solo.xml"
        xml.write_bytes(b"z" * 4096)
        assert _file_size_mb(xml) == pytest.approx(4096 / (1024.0 * 1024.0))


# ===========================================================================
# Benchmark validation + runner dispatch
# ===========================================================================


class TestBenchmarkValidation:
    def test_iterations_below_one_raises(self) -> None:
        # Line 254.
        with pytest.raises(ValueError, match="iterations must be >= 1"):
            Benchmark(runtime="callable", artifact=lambda x: x, input_shape=(1,), iterations=0)

    def test_warmup_below_zero_raises(self) -> None:
        # Line 256.
        with pytest.raises(ValueError, match="warmup must be >= 0"):
            Benchmark(runtime="callable", artifact=lambda x: x, input_shape=(1,), warmup=-1)

    def test_callable_requires_callable_artifact(self) -> None:
        # Line 487.
        bench_obj = Benchmark(runtime="callable", artifact=123, input_shape=(1,), warmup=0, iterations=1)
        with pytest.raises(ValueError, match="requires a callable artifact"):
            bench_obj.run()

    def test_onnxruntime_missing_dependency_raises(self, monkeypatch) -> None:
        # Line 419: guard fires when ORT is flagged unavailable.
        monkeypatch.setattr(bench, "_ORT_AVAILABLE", False)
        b = Benchmark(runtime="onnxruntime", artifact="whatever.onnx", input_shape=(1, 3, 4, 4),
                      warmup=0, iterations=1)
        with pytest.raises(ImportError, match="onnxruntime"):
            b.run()


class TestTorchIntegerInput:
    def test_torch_runner_integer_dtype(self) -> None:
        # Line 399: non-floating dtype path uses torch.randint.
        class IntSum(nn.Module):
            def forward(self, x: torch.Tensor) -> torch.Tensor:
                return x.float().sum().reshape(1)

        report = Benchmark(
            runtime="torch",
            artifact=IntSum(),
            input_shape=(1, 4),
            dtype="int64",
            warmup=1,
            iterations=3,
        ).run()
        assert report.iterations == 3
        assert report.fps > 0


class TestNumpyIntegerInput:
    def test_callable_integer_numpy_input(self) -> None:
        # Line 512: integer dtype input generated via rng.integers.
        captured = {}

        def grab(x: np.ndarray) -> np.ndarray:
            captured["dtype"] = x.dtype
            return x

        report = Benchmark(
            runtime="callable",
            artifact=grab,
            input_shape=(2, 2),
            dtype="int64",
            warmup=0,
            iterations=2,
        ).run()
        assert np.issubdtype(captured["dtype"], np.integer)
        assert report.iterations == 2


class TestOpenVinoRunner:
    """OpenVINO runtime with a mocked ``ov`` module (no real OpenVINO)."""

    def _install_fake_ov(self, monkeypatch):
        class FakeCompiled:
            def __call__(self, inputs):
                return {"out": np.ones((1, 2), dtype=np.float32)}

        class FakeCore:
            def compile_model(self, model, device_name):  # noqa: ARG002
                return FakeCompiled()

        class FakeOV:
            Core = FakeCore

        monkeypatch.setattr(bench, "ov", FakeOV)
        monkeypatch.setattr(bench, "_OV_AVAILABLE", True)

    def test_openvino_runner_runs(self, tmp_path: Path, monkeypatch) -> None:
        # Lines 379 (dispatch), 466 skip, 469-478 (compile + closure).
        self._install_fake_ov(monkeypatch)
        artifact = tmp_path / "model.onnx"
        artifact.write_bytes(b"0" * 2048)

        report = Benchmark(
            runtime="openvino",
            artifact=str(artifact),
            input_shape=(1, 3, 4, 4),
            device="cpu",
            warmup=1,
            iterations=3,
        ).run()
        assert report.runtime == "openvino"
        assert report.iterations == 3
        assert report.size_mb is not None and report.size_mb > 0

    def test_openvino_missing_dependency_raises(self, tmp_path: Path, monkeypatch) -> None:
        # Lines 466-467.
        monkeypatch.setattr(bench, "_OV_AVAILABLE", False)
        artifact = tmp_path / "model.onnx"
        artifact.write_bytes(b"0" * 16)
        b = Benchmark(runtime="openvino", artifact=str(artifact), input_shape=(1, 3, 4, 4),
                      warmup=0, iterations=1)
        with pytest.raises(ImportError, match="openvino"):
            b.run()


# ===========================================================================
# ptq.py — fake ONNX model structures for graph-input resolution
# ===========================================================================


class _Dim:
    def __init__(self, value=None) -> None:
        self._value = value

    def HasField(self, field: str) -> bool:  # noqa: N802 (mirror protobuf API)
        return field == "dim_value" and self._value is not None

    @property
    def dim_value(self) -> int:
        return self._value


class _Shape:
    def __init__(self, dims) -> None:
        self.dim = dims


class _TensorType:
    def __init__(self, dims) -> None:
        self.shape = _Shape(dims)


class _Type:
    def __init__(self, dims) -> None:
        self.tensor_type = _TensorType(dims)


class _Input:
    def __init__(self, name, dims) -> None:
        self.name = name
        self.type = _Type(dims)


class _Init:
    def __init__(self, name) -> None:
        self.name = name


class _Graph:
    def __init__(self, inputs, initializers) -> None:
        self.input = inputs
        self.initializer = initializers


class _Model:
    def __init__(self, graph) -> None:
        self.graph = graph


class TestResolveInputInfo:
    def test_skips_initializer_named_input(self, monkeypatch) -> None:
        # Line 91: an input whose name is an initializer is skipped.
        model = _Model(
            _Graph(
                inputs=[_Input("w", [_Dim(3)]), _Input("x", [_Dim(1), _Dim(3)])],
                initializers=[_Init("w")],
            )
        )
        monkeypatch.setattr(ptq.onnx, "load", lambda p: model)
        name, rank, batch = _resolve_input_info(Path("m.onnx"))
        assert name == "x"
        assert rank == 2
        assert batch == 1

    def test_dynamic_batch_dim_yields_none(self, monkeypatch) -> None:
        # Leading dim with no dim_value -> batch_size stays None.
        model = _Model(_Graph(inputs=[_Input("x", [_Dim(None), _Dim(3)])], initializers=[]))
        monkeypatch.setattr(ptq.onnx, "load", lambda p: model)
        name, rank, batch = _resolve_input_info(Path("m.onnx"))
        assert (name, rank, batch) == ("x", 2, None)

    def test_no_graph_input_raises(self, monkeypatch) -> None:
        # Line 100: every input is an initializer -> ValueError.
        model = _Model(_Graph(inputs=[_Input("w", [_Dim(3)])], initializers=[_Init("w")]))
        monkeypatch.setattr(ptq.onnx, "load", lambda p: model)
        with pytest.raises(ValueError, match="Could not find a graph input"):
            _resolve_input_info(Path("m.onnx"))

    def test_resolve_input_name(self, monkeypatch) -> None:
        # Line 115.
        model = _Model(_Graph(inputs=[_Input("images", [_Dim(1), _Dim(3)])], initializers=[]))
        monkeypatch.setattr(ptq.onnx, "load", lambda p: model)
        assert _resolve_input_name(Path("m.onnx")) == "images"


class TestBatchToArrays:
    def test_bare_int_array_cast_to_float(self) -> None:
        # Line 152 (float cast) and 174 (rank-unknown passthrough).
        feeds = _batch_to_arrays(np.arange(4, dtype=np.int64), "input")
        assert len(feeds) == 1
        assert feeds[0]["input"].dtype == np.float32

    def test_empty_sequence_returns_empty(self) -> None:
        # Line 160.
        assert _batch_to_arrays([], "input") == []

    def test_known_rank_mismatch_passthrough(self) -> None:
        # Line 170: ndim is neither sample_rank+1 nor sample_rank.
        arr = np.zeros((5,), dtype=np.float32)
        feeds = _batch_to_arrays(arr, "input", sample_rank=3)
        assert len(feeds) == 1
        assert feeds[0]["input"].shape == (5,)

    def test_known_rank_batched_splits(self) -> None:
        # Lines 166-167.
        arr = np.zeros((2, 3, 4, 4), dtype=np.float32)
        feeds = _batch_to_arrays(arr, "input", sample_rank=3)
        assert len(feeds) == 2
        assert all(f["input"].shape == (1, 3, 4, 4) for f in feeds)

    def test_known_rank_single_sample_gains_batch(self) -> None:
        # Lines 168-169.
        arr = np.zeros((3, 4, 4), dtype=np.float32)
        feeds = _batch_to_arrays(arr, "input", sample_rank=3)
        assert len(feeds) == 1
        assert feeds[0]["input"].shape == (1, 3, 4, 4)

    def test_unknown_rank_4d_splits(self) -> None:
        # Lines 172-173.
        arr = np.zeros((2, 3, 4, 4), dtype=np.float32)
        feeds = _batch_to_arrays(arr, "input")
        assert len(feeds) == 2


class TestCollectFeeds:
    def test_dict_feed_disables_regrouping(self) -> None:
        # Lines 227-228: a multi-key dict feed forces grouped = feeds; break.
        a = np.zeros((1, 3), dtype=np.float32)
        data = [
            {"input": a, "extra": a},
            {"input": a, "extra": a},
        ]
        feeds = collect_feeds(data, "input", 2, batch_size=2)
        assert len(feeds) == 2
        assert all("extra" in f for f in feeds)

    def test_no_feeds_raises(self) -> None:
        # Line 233.
        with pytest.raises(ValueError, match="No calibration samples"):
            collect_feeds([], "input", 5)


class TestFeedCalibrationReader:
    def test_rewind_replays_from_start(self) -> None:
        # Lines 253-259.
        f1 = {"input": np.zeros((1, 3), dtype=np.float32)}
        f2 = {"input": np.ones((1, 3), dtype=np.float32)}
        reader = FeedCalibrationReader([f1, f2])
        assert reader.get_next() is f1
        assert reader.get_next() is f2
        assert reader.get_next() is None
        reader.rewind()
        assert reader.get_next() is f1


class TestPreprocessFallback:
    def test_preprocess_failure_returns_original(self, tmp_path: Path, monkeypatch) -> None:
        # Lines 283-284: quant_pre_process raising falls back to the source path.
        def boom(*args, **kwargs):
            raise RuntimeError("shape inference failed")

        monkeypatch.setattr(ptq, "quant_pre_process", boom)
        src = tmp_path / "model.onnx"
        result = preprocess_for_quantization(src, tmp_path)
        assert result == src


class TestRequireOrtQuant:
    def test_raises_when_unavailable(self, monkeypatch) -> None:
        # Line 56.
        monkeypatch.setattr(ptq, "_ORT_QUANT_AVAILABLE", False)
        with pytest.raises(ImportError, match="ONNX quantization requires"):
            ptq._require_ort_quant()


class TestStaticQuantizerRun:
    def test_missing_model_file_raises(self, tmp_path: Path) -> None:
        # Line 423.
        quantizer = StaticQuantizer()
        with pytest.raises(FileNotFoundError, match="ONNX model not found"):
            quantizer.run(tmp_path / "nope.onnx", [np.zeros((1, 3, 4, 4), dtype=np.float32)])
