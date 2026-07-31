"""The typed optimization error hierarchy — granular reasons, ValueError-compatible."""

from __future__ import annotations

import pytest
import torch.nn as nn

from mindtrace.models.optimization import (
    CalibrationError,
    InvalidSchemeError,
    NumericalInstabilityError,
    OptimizationError,
    QuantScheme,
    UnsupportedModelError,
    UnsupportedOptimizationError,
    prepare_qat,
    to_precision,
    validate_optimization,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "err",
        [
            InvalidSchemeError,
            CalibrationError,
            UnsupportedModelError,
            UnsupportedOptimizationError,
            NumericalInstabilityError,
        ],
    )
    def test_all_are_optimization_errors(self, err):
        assert issubclass(err, OptimizationError)

    def test_optimization_error_is_valueerror(self):
        # Back-compat: existing `except ValueError` handlers still catch everything.
        assert issubclass(OptimizationError, ValueError)


class TestTypedRaises:
    def test_invalid_scheme_bits(self):
        with pytest.raises(InvalidSchemeError):
            QuantScheme(weight_bits=16)

    def test_invalid_target_type(self):
        model = nn.Sequential(nn.Linear(4, 4))
        with pytest.raises(InvalidSchemeError):
            prepare_qat(model, QuantScheme(target_types=("Conv2d",)))

    def test_invalid_precision(self):
        with pytest.raises(InvalidSchemeError):
            to_precision(nn.Linear(4, 4), "int3")

    def test_unsupported_optimization_still_typed(self):
        with pytest.raises(UnsupportedOptimizationError):
            validate_optimization("QAT", task="detection", provider="torchvision")

    def test_caught_as_valueerror(self):
        # The profiling sweep filters lossy variants via `except ValueError` — must still work.
        with pytest.raises(ValueError):
            QuantScheme(weight_bits=16)
