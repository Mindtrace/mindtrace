"""Network-flag selection and ONNX parsing for TensorRT — tested without a real TRT.

TensorRT 10 uses BuilderFlag.FP16/.INT8 (weakly-typed); TensorRT 11+ removed them and
requires a strongly-typed network for reduced precision. _resolve_network_flags picks
the right mode so half-precision engines don't silently fall back to fp32. Parsing goes
through parse_from_file so external-data weights resolve against the model's directory.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from mindtrace.models.optimization.compile.tensorrt import _parse_onnx_into_network, _resolve_network_flags
from mindtrace.models.optimization.targets import TargetSpec

EXPLICIT_BATCH = 0
STRONGLY_TYPED = 1


def _fake_trt(*, has_precision_flags: bool, has_strongly_typed: bool = True):
    ndcf = types.SimpleNamespace(EXPLICIT_BATCH=EXPLICIT_BATCH)
    if has_strongly_typed:
        ndcf.STRONGLY_TYPED = STRONGLY_TYPED
    builder_flag = types.SimpleNamespace()
    if has_precision_flags:
        builder_flag.FP16 = 4
        builder_flag.INT8 = 5
    return types.SimpleNamespace(NetworkDefinitionCreationFlag=ndcf, BuilderFlag=builder_flag)


def _target(*precisions):
    return TargetSpec(name="t", runtime="tensorrt", device="CUDA", precisions=tuple(precisions))


class TestResolveNetworkFlags:
    def test_trt10_fp16_uses_builder_flags_not_strongly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=True), _target("fp32", "fp16"), False)
        assert strong is False
        assert flags == (1 << EXPLICIT_BATCH)  # no strongly-typed bit

    def test_trt11_fp16_becomes_strongly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=False), _target("fp16"), False)
        assert strong is True
        assert flags & (1 << STRONGLY_TYPED)

    def test_explicit_override_forces_strongly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=True), _target("fp32"), True)
        assert strong is True

    def test_fp32_only_without_flags_stays_weakly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=False), _target("fp32"), False)
        assert strong is False

    def test_bf16_triggers_strongly_typed_on_trt11(self):
        _, strong = _resolve_network_flags(_fake_trt(has_precision_flags=False), _target("bf16"), False)
        assert strong is True

    def test_no_strongly_typed_support_falls_back(self):
        # A build with neither precision flags nor STRONGLY_TYPED: can't do half precision.
        _, strong = _resolve_network_flags(
            _fake_trt(has_precision_flags=False, has_strongly_typed=False), _target("fp16"), True
        )
        assert strong is False


# ---------------------------------------------------------------------------
# ONNX parsing (path-aware, external-data safe)
# ---------------------------------------------------------------------------


class _FakeLogger:
    INTERNAL_ERROR = 0
    WARNING = 2
    INFO = 3

    def __init__(self, _severity=0):
        pass

    def log(self, _severity, _msg):
        pass


class _FakeParser:
    """Mimics trt.OnnxParser: parse_from_file returns a preset result plus canned errors."""

    def __init__(self, network, _logger, result):
        self.network = network
        self._result = result
        self.parsed_path = None

    def parse_from_file(self, path):
        self.parsed_path = path
        return self._result

    @property
    def num_errors(self):
        return 2

    def get_error(self, i):
        return f"err{i}"


class _FakeBuilder:
    def __init__(self):
        self.networks = 0

    def create_network(self, _flags):
        self.networks += 1
        return f"network-{self.networks}"


def _fake_parse_trt(parse_result):
    parsers = []

    def make_parser(network, logger):
        p = _FakeParser(network, logger, parse_result)
        parsers.append(p)
        return p

    trt = types.SimpleNamespace(Logger=_FakeLogger, OnnxParser=make_parser)
    return trt, parsers


class TestParseOnnxIntoNetwork:
    """Parsing goes through parse_from_file so external-data weights resolve by path."""

    def test_returns_network_on_success(self):
        trt, parsers = _fake_parse_trt(True)
        builder = _FakeBuilder()
        net = _parse_onnx_into_network(trt, builder, _FakeLogger(), Path("dir/model.onnx"), 0)
        assert net == "network-1"
        assert builder.networks == 1
        assert parsers[0].parsed_path == "dir/model.onnx"  # parsed by path, not from bytes

    def test_raises_with_parser_errors_on_failure(self):
        trt, _ = _fake_parse_trt(False)
        with pytest.raises(RuntimeError, match="failed to parse.*err0; err1"):
            _parse_onnx_into_network(trt, _FakeBuilder(), _FakeLogger(), Path("model.onnx"), 0)
