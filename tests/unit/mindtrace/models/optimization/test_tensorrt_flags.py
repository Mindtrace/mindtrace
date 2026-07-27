"""Strongly-typed network selection for TensorRT — logic tested without a real TRT.

TensorRT 10 uses BuilderFlag.FP16/.INT8 (weakly-typed); TensorRT 11+ removed them and
requires a strongly-typed network for reduced precision. _resolve_network_flags picks
the right mode so half-precision engines don't silently fall back to fp32.
"""

from __future__ import annotations

import types

from mindtrace.models.optimization.compile.tensorrt import _resolve_network_flags
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
